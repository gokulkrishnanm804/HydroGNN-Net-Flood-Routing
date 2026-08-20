"""
HydroRIVERS v1.0 Shapefile Downloader and River Network Builder

Downloads and clips the HydroRIVERS Asia shapefile to the basin bounding box.
Used to determine upstream/downstream river connectivity between monitoring stations.

Data source (free, registration required): https://www.hydrosheds.org/products/hydrorivers
Reference:
    Lehner, B. & Grill, G. (2013). Global river hydrography and network routing:
    baseline data and new approaches to study the world's large river systems.
    Hydrological Processes, 27(15), 2171-2186.
    DOI: 10.1002/hyp.9740
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import pandas as pd

from src.downloaders.base import BaseDownloader
from src.utils.cache import CacheManager, DataSourceUnavailable
from src.utils.logger import DownloadLogger, get_logger

logger = get_logger(__name__)


class HydroRIVERSDownloader(BaseDownloader):
    """
    Downloads HydroRIVERS Asia shapefile and clips to basin bounding box.

    Requires geopandas: pip install geopandas
    """

    # URL is now read from config (hydrorivers.url) so it can be updated without code change
    SOURCE = "HydroRIVERS"

    def __init__(
        self,
        cache_manager: CacheManager,
        download_logger: DownloadLogger,
        config: dict,
    ) -> None:
        super().__init__(cache_manager, download_logger, config)
        self.bbox      = config["basin"]["bbox"]
        self.min_order = config.get("hydrorivers", {}).get("min_strahler_order", 3)
        # Read URL from config; fallback to known good URL
        self.URL = config.get("hydrorivers", {}).get(
            "url",
            "https://data.hydrosheds.org/file/HydroRIVERS/HydroRIVERS_v10_as_shp.zip",
        )

    # ------------------------------------------------------------------ #
    # Download
    # ------------------------------------------------------------------ #

    def download_hydrorivers(self, output_dir: Path) -> Path:
        """
        Download HydroRIVERS Asia ZIP and extract the shapefile.

        Returns path to extracted .shp file.
        """
        output_dir = Path(output_dir) / "hydrorivers_raw"
        output_dir.mkdir(parents=True, exist_ok=True)

        # Check if already extracted
        existing_shp = list(output_dir.glob("*.shp"))
        if existing_shp:
            logger.info(f"HydroRIVERS already extracted: {existing_shp[0]}")
            return existing_shp[0]

        zip_name  = Path(self.URL).name
        zip_path  = output_dir.parent / zip_name
        size_hint = "91MB"
        logger.info(f"Downloading HydroRIVERS ({size_hint}): {self.URL}")
        ok = self.download_file(self.URL, zip_path, source_label=self.SOURCE)

        if not ok or not zip_path.exists():
            raise DataSourceUnavailable(
                "HydroRIVERS download failed.\n"
                "\n"
                "Manual download option:\n"
                "  1. Register at https://www.hydrosheds.org (free)\n"
                "  2. Download HydroRIVERS Asia from the Products page\n"
                "  3. Extract the .shp file to: dataset/raw/hydrorivers/hydrorivers_raw/\n"
            )

        logger.info(f"Extracting HydroRIVERS ZIP…")
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(output_dir)

        shp_files = list(output_dir.rglob("*.shp"))
        if not shp_files:
            raise DataSourceUnavailable(
                f"No .shp file found after extracting {zip_path}\n"
                "Please verify the ZIP downloaded correctly."
            )
        return shp_files[0]

    # ------------------------------------------------------------------ #
    # Clip to basin
    # ------------------------------------------------------------------ #

    def clip_to_basin(
        self,
        shp_path: Path,
        bbox: list,
        output_path: Path,
    ):
        """
        Clip HydroRIVERS shapefile to basin bounding box.

        Parameters
        ----------
        shp_path    : Path to HydroRIVERS .shp file.
        bbox        : [lon_min, lat_min, lon_max, lat_max]
        output_path : Where to save clipped shapefile.

        Returns
        -------
        GeoDataFrame of clipped river network.
        """
        try:
            import geopandas as gpd
        except ImportError:
            raise DataSourceUnavailable(
                "geopandas is required for HydroRIVERS processing.\n"
                "Install: pip install geopandas"
            )

        logger.info(f"Reading HydroRIVERS shapefile…")
        gdf = gpd.read_file(shp_path)

        lon_min, lat_min, lon_max, lat_max = bbox
        # Add buffer
        buf = 0.5
        clipped = gdf.cx[lon_min - buf:lon_max + buf, lat_min - buf:lat_max + buf].copy()

        # Filter by Strahler order (keep major rivers)
        if "ORD_STRA" in clipped.columns:
            clipped = clipped[clipped["ORD_STRA"] >= self.min_order]

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        clipped.to_file(output_path)
        logger.info(f"Clipped to {len(clipped)} river segments -> {output_path}")
        return clipped

    # ------------------------------------------------------------------ #
    # Extract network
    # ------------------------------------------------------------------ #

    def extract_river_network(self, gdf) -> object:
        """
        Simplify HydroRIVERS GeoDataFrame to relevant columns.

        Keeps: MAIN_RIV, LENGTH_KM, DIST_DN_KM, ORD_STRA, geometry
        """
        keep = []
        for col in ["MAIN_RIV", "LENGTH_KM", "DIST_DN_KM", "ORD_STRA", "geometry"]:
            if col in gdf.columns:
                keep.append(col)
        return gdf[keep].copy()

    # ------------------------------------------------------------------ #
    # Station connectivity
    # ------------------------------------------------------------------ #

    def build_station_river_network(
        self,
        river_gdf,
        nodes_df: pd.DataFrame,
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Match stations to river segments and infer upstream/downstream order.

        Algorithm:
        1. For each station, find nearest river segment by geometry distance.
        2. Record the DIST_DN_KM (distance to river mouth) for each station.
        3. Stations on the same MAIN_RIV where dist_dn_km_i > dist_dn_km_j
           → station_i is upstream of station_j.
        4. Build edges only between direct neighbors (no skip connections).

        Parameters
        ----------
        river_gdf : Clipped HydroRIVERS GeoDataFrame.
        nodes_df  : Station DataFrame with columns [station_id, lat, lon, ...].

        Returns
        -------
        (edges_df, edge_attrs_df) with columns:
            edges_df      : src_id, dst_id
            edge_attrs_df : src_id, dst_id, length_km, elev_diff_m, travel_time_h, strahler_order
        """
        try:
            import geopandas as gpd
            from shapely.geometry import Point
        except ImportError:
            logger.warning("geopandas unavailable; returning empty edges")
            return pd.DataFrame(), pd.DataFrame()

        velocity_kmh = self.config["graph"]["default_velocity_kmh"]

        # Convert stations to GeoDataFrame
        stations_gdf = gpd.GeoDataFrame(
            nodes_df,
            geometry=[Point(row["lon"], row["lat"]) for _, row in nodes_df.iterrows()],
            crs="EPSG:4326",
        )

        # For each station, find nearest river segment
        if river_gdf.crs is None or river_gdf.crs.to_epsg() != 4326:
            river_gdf = river_gdf.to_crs("EPSG:4326")

        station_info = []
        for _, st in stations_gdf.iterrows():
            dists = river_gdf.geometry.distance(st.geometry)
            nearest_idx = dists.idxmin()
            nearest_seg = river_gdf.loc[nearest_idx]
            station_info.append({
                "station_id":   st["station_id"],
                "lat":          st["lat"],
                "lon":          st["lon"],
                "elevation_m":  st.get("elevation_m", 0),
                "main_riv":     nearest_seg.get("MAIN_RIV", 0),
                "dist_dn_km":   nearest_seg.get("DIST_DN_KM", 0),
                "strahler":     nearest_seg.get("ORD_STRA", 3),
            })

        info_df = pd.DataFrame(station_info).sort_values("dist_dn_km", ascending=False)

        # Build edges: station with higher dist_dn_km (farther from mouth) is upstream
        edges = []
        attrs = []

        for i, row_u in info_df.iterrows():
            for j, row_d in info_df.iterrows():
                if row_u["station_id"] == row_d["station_id"]:
                    continue
                if row_u["main_riv"] != row_d["main_riv"]:
                    continue
                if row_u["dist_dn_km"] <= row_d["dist_dn_km"]:
                    continue   # row_u must be upstream (larger dist to mouth)

                # Check if any intermediate station exists on this river
                intermediate = info_df[
                    (info_df["main_riv"] == row_u["main_riv"]) &
                    (info_df["dist_dn_km"] < row_u["dist_dn_km"]) &
                    (info_df["dist_dn_km"] > row_d["dist_dn_km"])
                ]
                if len(intermediate) > 0:
                    continue  # Skip: not direct neighbors

                dist_km   = row_u["dist_dn_km"] - row_d["dist_dn_km"]
                tt_h      = dist_km / velocity_kmh
                elev_diff = max(0.0, row_u["elevation_m"] - row_d["elevation_m"])

                edges.append({"src_id": row_u["station_id"], "dst_id": row_d["station_id"]})
                attrs.append({
                    "src_id":        row_u["station_id"],
                    "dst_id":        row_d["station_id"],
                    "length_km":     round(dist_km, 2),
                    "elev_diff_m":   round(elev_diff, 1),
                    "travel_time_h": round(tt_h, 3),
                    "strahler_order": int(row_u.get("strahler", 3)),
                })

        edges_df = pd.DataFrame(edges) if edges else pd.DataFrame(columns=["src_id", "dst_id"])
        attrs_df = pd.DataFrame(attrs) if attrs else pd.DataFrame()
        logger.info(f"HydroRIVERS: built {len(edges_df)} directed edges from {len(info_df)} stations")
        return edges_df, attrs_df
