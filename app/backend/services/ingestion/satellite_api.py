"""
Copernicus Sentinel-2 satellite scene ingestion.

Strategy order (fastest / most reliable first):
  1. STAC POST search  — https://stac.dataspace.copernicus.eu/v1/search (new 2024 endpoint)
  2. OData global      — fallback; slow but sometimes works

Both return the same normalised dict so the writer code is unchanged.
"""
import json
import time
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.backend.services.db.models import SatelliteImage, RiverStation
from app.backend.services.logging_manager import api_logger

# ── Endpoint URLs ──────────────────────────────────────────────────────────────
# New (2024) STAC endpoint — the old catalogue.dataspace.copernicus.eu/stac is deprecated
COPERNICUS_STAC_SEARCH = "https://stac.dataspace.copernicus.eu/v1/search"

# OData endpoint — kept as last-resort; very slow (30-60s per call)
COPERNICUS_ODATA_BASE  = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"

# Timeouts
STAC_TIMEOUT_SEC  = 20   # STAC is fast when it works
ODATA_TIMEOUT_SEC = 10   # Short: we'd rather skip than block the scheduler


def _build_odata_url(filter_str: str, orderby: str = "ContentDate/Start desc",
                     top: int = 1) -> str:
    """Build an OData URL with all parameters percent-encoded (avoids http.client control-char rejection)."""
    params = urllib.parse.urlencode({
        "$filter":  filter_str,
        "$orderby": orderby,
        "$top":     str(top),
        "$format":  "json",
    })
    return f"{COPERNICUS_ODATA_BASE}?{params}"


def _stac_search(bbox: list, max_items: int = 1) -> list:
    """
    Strategy 1 — POST to new STAC endpoint.
    Collection: sentinel-2-l2a  (Sentinel-2 Level-2A, confirmed CDSE collection ID)
    bbox = [min_lon, min_lat, max_lon, max_lat]
    Returns list of normalised dicts (same schema as OData fallback).
    """
    # Date range: last 30 days to ensure recent imagery
    end_dt   = datetime.utcnow()
    start_dt = end_dt - timedelta(days=30)
    body = json.dumps({
        "collections": ["sentinel-2-l2a"],
        "bbox":         bbox,
        "limit":        max_items,
        "datetime":     f"{start_dt.strftime('%Y-%m-%dT%H:%M:%SZ')}/{end_dt.strftime('%Y-%m-%dT%H:%M:%SZ')}",
    }).encode()

    t0 = time.time()
    try:
        req = urllib.request.Request(
            COPERNICUS_STAC_SEARCH, data=body,
            headers={
                "User-Agent":   "HydroGNN-Net/1.0",
                "Accept":       "application/geo+json",
                "Content-Type": "application/json",
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=STAC_TIMEOUT_SEC) as res:
            ms      = round((time.time() - t0) * 1000)
            data    = json.loads(res.read().decode("utf-8"))
            feats   = data.get("features", [])
            api_logger.info(
                f"[STAC] POST search HTTP 200 in {ms}ms | {len(feats)} features | bbox={bbox}"
            )
            results = []
            for f in feats:
                props = f.get("properties", {})
                results.append({
                    "Id":          f.get("id", ""),
                    "Name":        props.get("title", f.get("id", "S2_scene")),
                    "ContentDate": {"Start": props.get("datetime", "")},
                    "Online":      True,
                    "_source":     "stac",
                })
            return results
    except urllib.error.HTTPError as e:
        ms   = round((time.time() - t0) * 1000)
        body_text = e.read().decode()
        api_logger.warning(
            f"[STAC] HTTP {e.code} in {ms}ms: {body_text[:200]}"
        )
        return []
    except Exception as e:
        ms = round((time.time() - t0) * 1000)
        api_logger.warning(f"[STAC] Failed in {ms}ms: {e}")
        return []


def _odata_global_fallback() -> list:
    """
    Strategy 2 — OData global latest S2 scene (no spatial filter to reduce query complexity).
    Short 10s timeout: we skip rather than block the scheduler for a whole minute.
    """
    filter_str   = "startswith(Name,'S2')"
    fallback_url = _build_odata_url(filter_str=filter_str, top=1)
    t0 = time.time()
    try:
        req = urllib.request.Request(fallback_url, headers={"User-Agent": "HydroGNN-Net/1.0"})
        with urllib.request.urlopen(req, timeout=ODATA_TIMEOUT_SEC) as res:
            ms    = round((time.time() - t0) * 1000)
            data  = json.loads(res.read().decode("utf-8"))
            items = data.get("value", [])
            api_logger.info(
                f"[OData] Global fallback HTTP 200 in {ms}ms | {len(items)} products"
            )
            return items
    except Exception as e:
        ms = round((time.time() - t0) * 1000)
        api_logger.warning(f"[OData] Global fallback failed in {ms}ms: {e}")
        return []


def fetch_and_store_satellite(db: Session, ts: datetime):
    """
    Ingests Sentinel-2 scene metadata from Copernicus into satellite_images table.
    Runs at scheduler noon tick (or on-demand from /api/satellite when table is empty).

    Strategy:
      1. STAC POST search (new endpoint, fast, per-station bbox)
      2. OData global latest S2 scene (slow fallback, shared across all stations)
    """
    print(f"[{ts.strftime('%Y-%m-%d %H:%M:%S')}] Checking Sentinel-2 passes via Copernicus STAC...")

    # Daily time-gate: only execute once per day at noon OR if called on-demand
    # (on-demand means ts.hour == 12 from the satellite router)
    if ts.hour != 12:
        return

    stations   = db.query(RiverStation).all()
    registered = 0

    # ── Strategy 2 pre-fetch (OData global) — try once, share result ──────────
    # We fetch it ONCE here (not per-station) to avoid hammering OData.
    odata_global = None   # lazy: only fetch if STAC fails for every station

    for s in stations:
        lon, lat = s.lon, s.lat
        d    = 0.2   # ±0.2° bounding box (~22 km) — bigger box = more results
        bbox = [round(lon - d, 4), round(lat - d, 4),
                round(lon + d, 4), round(lat + d, 4)]

        # Strategy 1: STAC POST
        api_logger.info(f"[{s.name}] Strategy 1: STAC POST search bbox={bbox}")
        items = _stac_search(bbox, max_items=1)

        # Strategy 2: OData global (shared single fetch)
        if not items:
            api_logger.warning(f"[{s.name}] STAC returned 0 features. Trying OData global fallback.")
            if odata_global is None:
                odata_global = _odata_global_fallback()
            items = odata_global  # all stations share the same global product

        if items:
            prod = items[0]
            prod_id   = prod.get("Id",   f"unknown_{ts.strftime('%Y%m%d')}")
            prod_name = prod.get("Name", "S2A_Scene")

            # Parse capture date safely
            dt_str = prod.get("ContentDate", {}).get("Start", ts.isoformat())
            try:
                cap_date = datetime.strptime(
                    dt_str.split(".")[0].replace("Z", ""), "%Y-%m-%dT%H:%M:%S"
                ).date()
            except Exception:
                cap_date = ts.date()

            # Use station_id + capture_date as the unique key (never collides,
            # always fits in String(50), and is human-readable).
            img_id = f"SAT_{s.id}_{cap_date.strftime('%Y%m%d')}"[:50]
            exists = db.query(SatelliteImage).filter(SatelliteImage.id == img_id).first()
            if not exists:
                src = "Sentinel-2 L2A (STAC)" if prod.get("_source") == "stac" \
                      else "Sentinel-2 L2A (OData)"
                image_rec = SatelliteImage(
                    id           = img_id,
                    station_id   = s.id,
                    capture_date = cap_date,
                    source       = src,
                    storage_path = f"gis/satellite/tiles/{img_id}.tif"
                )
                db.add(image_rec)
                db.commit()          # commit per-station — safe with SQLite WAL
                registered += 1
                api_logger.info(f"Registered Sentinel-2 scene for {s.name}: {prod_name} ({cap_date})")
                print(f"  [OK] {s.name}: {prod_name} ({cap_date})")
            else:
                print(f"  [SKIP] Already in DB: {s.name}: {img_id}")
        else:
            api_logger.warning(
                f"Copernicus: no scenes available for {s.name} (STAC + OData both failed). Skipping."
            )
            print(f"  [WARN] No Sentinel-2 scene for {s.name} -- will retry next scheduler tick.")

    print(f"  Satellite ingestion complete. Registered {registered} new scenes.")
