"""
SRTM 30m Digital Elevation Model Downloader and Terrain Attribute Processor

Uses the 'elevation' Python package to download SRTM1 tiles (1 arc-second ≈ 30m).
Computes terrain attributes: slope.

Reference:
    Farr, T.G. et al. (2007). The Shuttle Radar Topography Mission.
    Reviews of Geophysics, 45(2). DOI: 10.1029/2005RG000183
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from src.utils.cache import CacheManager, DataSourceUnavailable
from src.utils.logger import DownloadLogger, get_logger

logger = get_logger(__name__)


class SRTMDownloader:
    """
    Downloads SRTM DEM tiles and computes terrain attributes.

    Requires 'elevation' package: pip install elevation
    Also requires GDAL: pip install GDAL (or use conda)
    """

    def __init__(
        self,
        config: dict,
        cache_manager: CacheManager,
        download_logger: DownloadLogger,
    ) -> None:
        self.config  = config
        self.cache   = cache_manager
        self.dl_log  = download_logger
        self.raw_dir = Path(config["paths"]["raw_dir"]) / "srtm"
        self.raw_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    # Download
    # ------------------------------------------------------------------ #

    def download_basin_dem(self, bbox: list, output_path: Path) -> Path:
        """
        Download SRTM1 DEM for the basin bounding box via direct CGIAR tile download.

        Uses CGIAR-CSI SRTM 90m tiles (1-degree × 1-degree) directly.
        Mosaics tiles and reprojects to GeoTIFF.

        For the Cauvery basin (lon 74.5–81, lat 9.5–14):
          CGIAR tiles: 48_08 through 50_09 (approx. 6 tiles at 5-degree spacing)

        Tile naming: srtm_{xx}_{yy} where
          xx = floor((lon + 180) / 5) + 1  (1-72)
          yy = floor((60 - lat) / 5) + 1   (1-24)

        Parameters
        ----------
        bbox        : [lon_min, lat_min, lon_max, lat_max]
        output_path : Destination .tif file path.

        Returns
        -------
        Path to the mosaiced DEM GeoTIFF.
        """
        output_path = Path(output_path)
        if output_path.exists() and output_path.stat().st_size > 0:
            logger.info(f"SRTM DEM already exists: {output_path}")
            return output_path

        try:
            import rasterio
            from rasterio.merge import merge as rio_merge
        except ImportError:
            raise DataSourceUnavailable(
                "rasterio is required for SRTM processing.\n"
                "Install: pip install rasterio"
            )

        import zipfile, io
        import requests

        lon_min, lat_min, lon_max, lat_max = bbox
        buf = self.config.get("basin", {}).get("area_buffer_deg", 0.0)
        lon_min -= buf; lat_min -= buf
        lon_max += buf; lat_max += buf

        # Compute CGIAR tile IDs covering the bounding box
        # xx: 1-72, step of 5 degrees, starting at lon=-180
        # yy: 1-24, step of 5 degrees, starting at lat=60 (decreasing)
        def _tile_ids(lon_min, lat_min, lon_max, lat_max):
            xx_min = int((lon_min + 180) / 5) + 1
            xx_max = int((lon_max + 180) / 5) + 1
            yy_min = int((60 - lat_max) / 5) + 1
            yy_max = int((60 - lat_min) / 5) + 1
            tiles = []
            for xx in range(xx_min, xx_max + 1):
                for yy in range(yy_min, yy_max + 1):
                    tiles.append((xx, yy))
            return tiles

        tiles = _tile_ids(lon_min, lat_min, lon_max, lat_max)
        logger.info(f"SRTM: downloading {len(tiles)} CGIAR tiles for bbox {bbox}")

        tile_dir = output_path.parent / "srtm_tiles"
        tile_dir.mkdir(parents=True, exist_ok=True)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        downloaded_tifs = []
        for (xx, yy) in tiles:
            tile_name = f"srtm_{xx:02d}_{yy:02d}"
            tif_path  = tile_dir / f"{tile_name}.tif"

            if tif_path.exists() and tif_path.stat().st_size > 1000:
                logger.debug(f"  Tile {tile_name}: already cached")
                downloaded_tifs.append(tif_path)
                continue

            # Try CGIAR server first
            urls = [
                f"https://srtm.csi.cgiar.org/wp-content/uploads/files/srtm_5x5/TIFF/{tile_name}.zip",
                f"https://data.hydrosheds.org/file/hydrodem/hyd_as_dem_30s.zip",  # Fallback: HydroSHEDS
            ]
            ok = False
            for url in urls[:1]:  # CGIAR only for SRTM
                try:
                    logger.info(f"  Downloading {tile_name} from {url}")
                    resp = requests.get(url, timeout=60, stream=True)
                    resp.raise_for_status()
                    # Extract TIF from ZIP
                    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
                        tif_members = [n for n in zf.namelist() if n.endswith(".tif")]
                        if tif_members:
                            with zf.open(tif_members[0]) as src_f:
                                tif_path.write_bytes(src_f.read())
                            logger.info(f"  Tile {tile_name} extracted: {tif_path.stat().st_size/1e6:.1f} MB")
                            downloaded_tifs.append(tif_path)
                            ok = True
                    break
                except Exception as exc:
                    logger.warning(f"  Tile {tile_name} failed: {exc}")

            if not ok:
                logger.warning(f"  Tile {tile_name} unavailable — will use NaN for missing area")

        if not downloaded_tifs:
            raise DataSourceUnavailable(
                "No SRTM tiles could be downloaded.\n"
                "Manual option: download tiles from https://srtm.csi.cgiar.org/srtmdata/\n"
                f"Required tiles: {tiles}\n"
                f"Save extracted .tif files to: {tile_dir}\n"
                f"Then re-run the download."
            )

        # Mosaic tiles
        if len(downloaded_tifs) == 1:
            import shutil
            shutil.copy2(downloaded_tifs[0], output_path)
        else:
            logger.info(f"Mosaicing {len(downloaded_tifs)} SRTM tiles...")
            datasets = [rasterio.open(p) for p in downloaded_tifs]
            mosaic, transform = rio_merge(datasets)
            profile = datasets[0].profile.copy()
            profile.update({
                "height": mosaic.shape[1],
                "width":  mosaic.shape[2],
                "transform": transform,
            })
            with rasterio.open(output_path, "w", **profile) as dst:
                dst.write(mosaic)
            for ds in datasets:
                ds.close()

        logger.info(f"SRTM DEM saved: {output_path} ({output_path.stat().st_size/1e6:.1f} MB)")
        return output_path


    # ------------------------------------------------------------------ #
    # Terrain attributes
    # ------------------------------------------------------------------ #

    def compute_terrain_attributes(
        self,
        dem_path: Path,
        output_dir: Path,
    ) -> Dict[str, Path]:
        """
        Compute terrain slope from the SRTM DEM.

        Algorithm:
        - Slope in degrees using numpy gradient on the elevation grid.
        - Pixel size in meters: derived from the raster transform.
        - Uses finite differences: dy, dx = np.gradient(dem, pixel_size_y, pixel_size_x)
        - slope = arctan(sqrt(dx² + dy²)) in degrees.

        Parameters
        ----------
        dem_path   : Path to DEM GeoTIFF.
        output_dir : Directory to save computed attributes.

        Returns
        -------
        dict {'slope': slope_path, 'dem': dem_path}
        """
        try:
            import rasterio
            from rasterio.transform import from_bounds
        except ImportError:
            raise DataSourceUnavailable(
                "rasterio is required for terrain processing.\n"
                "Install: pip install rasterio"
            )

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        slope_path = output_dir / "slope.tif"

        logger.info(f"Computing terrain slope from {dem_path.name}…")

        with rasterio.open(dem_path) as src:
            dem_arr   = src.read(1).astype(float)
            transform = src.transform
            profile   = src.profile.copy()
            nodata    = src.nodata

        # Replace nodata with NaN
        if nodata is not None:
            dem_arr[dem_arr == nodata] = np.nan

        # Pixel size in meters (approximate at equator; adequate for ~30m SRTM)
        # transform[0] = pixel width in degrees (x), transform[4] = pixel height (negative)
        pixel_size_x = abs(transform[0]) * 111320.0  # m/degree longitude
        pixel_size_y = abs(transform[4]) * 111320.0  # m/degree latitude

        # Compute gradient
        dy, dx = np.gradient(dem_arr, pixel_size_y, pixel_size_x)
        slope  = np.degrees(np.arctan(np.sqrt(dx ** 2 + dy ** 2)))
        slope  = np.clip(slope, 0, 90)  # physical range

        # Save slope raster
        profile.update(dtype="float32", nodata=-9999.0)
        with rasterio.open(slope_path, "w", **profile) as dst:
            out = slope.astype("float32")
            out[np.isnan(slope)] = -9999.0
            dst.write(out, 1)

        logger.info(
            f"Slope computed: min={np.nanmin(slope):.2f}°, "
            f"max={np.nanmax(slope):.2f}°, "
            f"mean={np.nanmean(slope):.2f}°"
        )
        return {"slope": slope_path, "dem": dem_path}

    # ------------------------------------------------------------------ #
    # Station extraction
    # ------------------------------------------------------------------ #

    def extract_station_terrain(
        self,
        dem_path: Path,
        slope_path: Path,
        station_ids: List[str],
        station_coords: List[Tuple[float, float]],
    ) -> pd.DataFrame:
        """
        Extract elevation and slope at each station coordinate.

        Uses nearest-pixel lookup via rasterio.transform.rowcol.
        Returns NaN for stations outside the DEM extent (with WARNING).

        Parameters
        ----------
        dem_path      : DEM GeoTIFF path.
        slope_path    : Slope GeoTIFF path (from compute_terrain_attributes).
        station_ids   : List of station ID strings.
        station_coords: List of (lat, lon) tuples.

        Returns
        -------
        pd.DataFrame columns: [station_id, elevation_m, slope_deg]
        """
        try:
            import rasterio
        except ImportError:
            raise DataSourceUnavailable("rasterio required: pip install rasterio")

        records = []
        with rasterio.open(dem_path) as dem_src, rasterio.open(slope_path) as slp_src:
            dem_arr = dem_src.read(1).astype(float)
            slp_arr = slp_src.read(1).astype(float)
            dem_nd  = dem_src.nodata
            slp_nd  = slp_src.nodata
            if dem_nd is not None:
                dem_arr[dem_arr == dem_nd] = np.nan
            if slp_nd is not None:
                slp_arr[slp_arr == slp_nd] = np.nan

            for sid, (slat, slon) in zip(station_ids, station_coords):
                try:
                    row, col = rasterio.transform.rowcol(dem_src.transform, slon, slat)
                    nrow, ncol = dem_arr.shape
                    if 0 <= row < nrow and 0 <= col < ncol:
                        elev  = float(dem_arr[row, col])
                        slope = float(slp_arr[row, col])
                    else:
                        logger.warning(f"Station {sid} ({slat:.4f}°N, {slon:.4f}°E) outside DEM extent")
                        elev  = float("nan")
                        slope = float("nan")
                except Exception as exc:
                    logger.warning(f"Terrain extraction failed for {sid}: {exc}")
                    elev  = float("nan")
                    slope = float("nan")

                records.append({
                    "station_id":  sid,
                    "elevation_m": elev,
                    "slope_deg":   slope,
                })

        df = pd.DataFrame(records)
        logger.info(
            f"Terrain extracted for {len(df)} stations: "
            f"elev range [{df['elevation_m'].min():.0f}–{df['elevation_m'].max():.0f}] m"
        )
        return df

    # ------------------------------------------------------------------ #
    # Save
    # ------------------------------------------------------------------ #

    def save_station_terrain(self, df: pd.DataFrame, output_dir: Path) -> None:
        """Save terrain attributes CSV."""
        out = Path(output_dir) / "terrain_attributes.csv"
        out.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(out, index=False)
        logger.info(f"Terrain attributes saved: {out}")
