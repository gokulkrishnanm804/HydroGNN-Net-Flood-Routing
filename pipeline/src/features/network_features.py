"""
Network-based features for HydroGNN-Net.

Computes upstream flow contribution (lag-corrected) and reservoir influence index.
All values are derived from real CWC gauge and reservoir data.
If upstream data is unavailable, returns NaN with WARNING (never fabricates).
"""
import numpy as np
import pandas as pd
from typing import Dict, Optional, Tuple
from src.utils.logger import get_logger

logger = get_logger(__name__)


class NetworkFeatureComputer:
    """
    Computes network-based hydrological features.

    Parameters
    ----------
    edges_df       : DataFrame with columns [src_id, dst_id, travel_time_h]
    reservoir_data : dict of {reservoir_id: pd.DataFrame(storage_pct, release_cumecs)}
    station_res_map: dict of {station_id: reservoir_id} (nearest reservoir)
    upstream_tau_h : Decay constant for upstream contribution (hours)
    """

    def __init__(
        self,
        edges_df: pd.DataFrame,
        reservoir_data: Dict[str, pd.DataFrame],
        station_res_map: Dict[str, str],
        upstream_tau_h: float = 12.0,
    ) -> None:
        if upstream_tau_h <= 0:
            raise ValueError(f"upstream_tau_h must be positive. Got: {upstream_tau_h}")
        self.edges = edges_df
        self.reservoir_data = reservoir_data
        self.station_res_map = station_res_map
        self.tau = upstream_tau_h

    # ------------------------------------------------------------------
    # Graph topology helpers
    # ------------------------------------------------------------------

    def get_upstream_stations(self, station_id: str) -> list:
        """Return list of direct upstream neighbour station IDs."""
        if self.edges is None or len(self.edges) == 0:
            return []
        mask = self.edges['dst_id'] == station_id
        return list(self.edges.loc[mask, 'src_id'])

    def get_travel_time(self, src_id: str, dst_id: str) -> float:
        """
        Return travel time in hours between src and dst station.

        Falls back to 6.0 h if the edge is not found (logs a warning).
        """
        mask = (self.edges['src_id'] == src_id) & (self.edges['dst_id'] == dst_id)
        rows = self.edges.loc[mask, 'travel_time_h']
        if len(rows) == 0:
            logger.warning(
                f"No edge found ({src_id} -> {dst_id}). "
                "Defaulting travel_time_h=6.0."
            )
            return 6.0
        return float(rows.iloc[0])

    # ------------------------------------------------------------------
    # Upstream contribution
    # ------------------------------------------------------------------

    def compute_upstream_contribution_series(
        self,
        station_id: str,
        discharge_data: Dict[str, pd.DataFrame],
        timestamps: pd.DatetimeIndex,
    ) -> pd.Series:
        """
        Compute time series of lag-corrected upstream discharge contribution.

        For each upstream station u with travel time T_u:
            Q_upstream(t) = Q_u(t - T_u) * exp(-T_u / tau)

        Total contribution = sum over all upstream stations.

        If discharge data is missing for an upstream station, returns NaN for
        that station's contribution (logs WARNING, never fabricates data).

        Parameters
        ----------
        station_id     : Target station ID
        discharge_data : dict of {station_id: DataFrame} with 'discharge_cumecs' column
        timestamps     : DatetimeIndex for the output series

        Returns
        -------
        pd.Series with index=timestamps, name='upstream_contribution'
        """
        upstream = self.get_upstream_stations(station_id)

        if not upstream:
            logger.debug(
                f"Station {station_id}: no upstream neighbours. "
                "upstream_contribution=0.0"
            )
            return pd.Series(0.0, index=timestamps, name='upstream_contribution')

        contributions: list[pd.Series] = []

        for us_id in upstream:
            if us_id not in discharge_data:
                logger.warning(
                    f"Upstream station {us_id} -> {station_id}: "
                    "discharge data unavailable. Contributing NaN."
                )
                contributions.append(
                    pd.Series(np.nan, index=timestamps, name=us_id)
                )
                continue

            tt_h = self.get_travel_time(us_id, station_id)
            lag_steps = int(round(tt_h * 2))       # 30-min steps
            weight = np.exp(-tt_h / self.tau)

            q_us = (
                discharge_data[us_id]['discharge_cumecs']
                .reindex(timestamps)
            )
            # Positive shift looks back in time (upstream happened earlier)
            q_lagged = q_us.shift(lag_steps) * weight
            contributions.append(q_lagged.rename(us_id))

            logger.debug(
                f"  {us_id} -> {station_id}: "
                f"tt={tt_h:.1f}h, lag={lag_steps} steps, weight={weight:.4f}"
            )

        if not contributions:
            return pd.Series(0.0, index=timestamps, name='upstream_contribution')

        total: pd.Series = contributions[0]
        for s in contributions[1:]:
            total = total.add(s, fill_value=np.nan)

        total.name = 'upstream_contribution'
        return total

    # ------------------------------------------------------------------
    # Reservoir influence
    # ------------------------------------------------------------------

    def compute_reservoir_influence(
        self,
        station_id: str,
        timestamps: pd.DatetimeIndex,
    ) -> Tuple[pd.Series, pd.Series]:
        """
        Compute reservoir release and storage normalised by historical maximum.

        Normalisation:
          release_norm = release_cumecs / P99(release_cumecs)  clipped [0, 2]
          storage_norm = storage_pct    / 100.0                clipped [0, 1.2]

        Returns
        -------
        (release_norm, storage_norm) as pd.Series with index=timestamps.
        Both series are 0.0 if no reservoir data is available (logs WARNING).
        """
        res_id = self.station_res_map.get(station_id)
        zero = pd.Series(0.0, index=timestamps)

        if res_id is None:
            return (
                zero.rename('reservoir_release_norm'),
                zero.rename('reservoir_storage_norm'),
            )

        if res_id not in self.reservoir_data:
            logger.warning(
                f"No data for reservoir '{res_id}' (nearest to {station_id}). "
                "Using zeros."
            )
            return (
                zero.rename('reservoir_release_norm'),
                zero.rename('reservoir_storage_norm'),
            )

        res_df = self.reservoir_data[res_id].reindex(timestamps)

        # Use P99 as robust maximum to avoid division by extreme outliers
        max_release = res_df['release_cumecs'].quantile(0.99)
        if max_release <= 0:
            logger.warning(
                f"Reservoir '{res_id}' P99 release ≤ 0. "
                "Clamping denominator to 1."
            )
            max_release = 1.0

        max_storage = 100.0  # storage_pct is already 0–100

        rel_norm = (res_df['release_cumecs'] / max_release).clip(0.0, 2.0)
        sto_norm = (res_df['storage_pct'] / max_storage).clip(0.0, 1.2)

        return (
            rel_norm.rename('reservoir_release_norm'),
            sto_norm.rename('reservoir_storage_norm'),
        )

    # ------------------------------------------------------------------
    # Combined entry point
    # ------------------------------------------------------------------

    def compute_all_for_station(
        self,
        station_id: str,
        station_df: pd.DataFrame,
        discharge_data: Dict[str, pd.DataFrame],
        timestamps: pd.DatetimeIndex,
    ) -> pd.DataFrame:
        """
        Compute all network features for a single station.

        Returns
        -------
        pd.DataFrame with columns:
            upstream_contribution, reservoir_release_norm, reservoir_storage_norm
        """
        upstream = self.compute_upstream_contribution_series(
            station_id, discharge_data, timestamps
        )
        rel_norm, sto_norm = self.compute_reservoir_influence(station_id, timestamps)

        result = pd.DataFrame(
            {
                'upstream_contribution': upstream,
                'reservoir_release_norm': rel_norm,
                'reservoir_storage_norm': sto_norm,
            },
            index=timestamps,
        )

        nan_frac = result.isna().mean()
        for col, frac in nan_frac.items():
            if frac > 0:
                logger.warning(
                    f"Station {station_id} | {col}: {frac * 100:.1f}% NaN values"
                )

        return result
