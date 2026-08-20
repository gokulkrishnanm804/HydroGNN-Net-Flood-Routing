"""
HydroGNN-Net Research Pipeline — Base Downloader

Provides resume-capable, retry-safe HTTP download functionality with:
- Exponential back-off retries (configurable attempts and delay)
- Range-based resume for interrupted downloads
- tqdm progress bars per file
- Parallel downloads via ThreadPoolExecutor with rate limiting
- Automatic .partial temp file management
- Integration with CacheManager and DownloadLogger
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

import requests
from requests import Session
from requests.adapters import HTTPAdapter
from tqdm import tqdm

from src.utils.cache import CacheManager
from src.utils.logger import DownloadLogger, get_logger

logger = get_logger(__name__)

_DEFAULT_HEADERS = {
    "User-Agent": "HydroGNN-Net/1.0 (IEEE Research Project; +https://github.com/hydrognn)",
}

# Session cache: keyed by (username, password)
_SESSION_CACHE: dict = {}


def _get_earthdata_session(auth: Optional[tuple]) -> Session:
    """
    Build a requests.Session for NASA Earthdata GES DISC.

    NASA GES DISC uses a two-step OAuth redirect:
      Step 1 — GET data URL → 302 redirect to urs.earthdata.nasa.gov/oauth/authorize
      Step 2 — URS checks session.auth credentials → 302 redirect back to GES DISC
      Step 3 — GES DISC delivers the file with a session cookie set

    The key requirement (from NASA docs) is that session.auth must be set on
    the session object itself (not per-request), so that `requests` sends
    the Authorization header when following the redirect to urs.earthdata.nasa.gov.

    After the first successful auth, the URS session cookie is stored in
    session.cookies and reused for all subsequent requests — no more 401s.
    """
    key = auth if auth else "anonymous"
    if key not in _SESSION_CACHE:
        session = Session()
        session.headers.update(_DEFAULT_HEADERS)
        if auth:
            # Set auth on the session — sent automatically on redirect to URS
            session.auth = auth
        _SESSION_CACHE[key] = session
        logger.debug("Created new Earthdata session")
    return _SESSION_CACHE[key]


class BaseDownloader:
    """
    Base class for all HydroGNN-Net data downloaders.

    Parameters
    ----------
    cache_manager    : CacheManager instance for checksum caching.
    download_logger  : DownloadLogger for CSV audit trail.
    config           : Pipeline config dict (from config.yaml).
    max_workers      : Default parallel worker count.
    """

    def __init__(
        self,
        cache_manager: CacheManager,
        download_logger: DownloadLogger,
        config: dict,
        max_workers: int = 4,
    ) -> None:
        self.cache = cache_manager
        self.dl_log = download_logger
        self.config = config
        self.max_workers = max_workers

        dl_cfg = config.get("download", {})
        self.retry_attempts  = int(dl_cfg.get("retry_attempts", 5))
        self.retry_delay     = float(dl_cfg.get("retry_delay_sec", 10.0))
        self.retry_backoff   = float(dl_cfg.get("retry_backoff", 2.0))
        self.chunk_size      = int(dl_cfg.get("chunk_size_bytes", 1_048_576))
        self.timeout         = int(dl_cfg.get("timeout_sec", 300))
        self.rate_limit_delay = float(dl_cfg.get("rate_limit_delay_sec", 1.0))

    # ------------------------------------------------------------------ #
    # Single-file download
    # ------------------------------------------------------------------ #

    def download_file(
        self,
        url: str,
        dest_path: Path,
        headers: Optional[dict] = None,
        auth: Optional[tuple] = None,
        resume: bool = True,
        source_label: str = "generic",
    ) -> bool:
        """
        Download *url* to *dest_path* with retry and resume support.

        The file is first written to ``dest_path + ".partial"`` and renamed
        on successful completion.

        Parameters
        ----------
        url          : HTTP(S) URL to download.
        dest_path    : Final destination path.
        headers      : Extra HTTP headers (merged with default User-Agent).
        auth         : (username, password) tuple for HTTP Basic Auth.
        resume       : If True, send Range header to resume partial downloads.
        source_label : Human-readable data source name for logging.

        Returns
        -------
        bool  True on success, False on failure after all retries.
        """
        dest_path = Path(dest_path)
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        # ── Already downloaded? ───────────────────────────────────────────
        if dest_path.exists() and dest_path.stat().st_size > 0:
            if self.cache.is_cached(url, dest_path):
                self.dl_log.log(source_label, dest_path.name, url, "SKIPPED")
                logger.debug(f"SKIP (cached): {dest_path.name}")
                return True

        partial = self.cache.partial_path(dest_path)
        merged_headers = {**_DEFAULT_HEADERS, **(headers or {})}

        for attempt in range(1, self.retry_attempts + 1):
            start_t = time.monotonic()
            try:
                # ── Resume? ───────────────────────────────────────────────
                resume_pos = 0
                if resume and partial.exists():
                    resume_pos = partial.stat().st_size
                    merged_headers["Range"] = f"bytes={resume_pos}-"
                    logger.debug(f"Resuming {dest_path.name} from byte {resume_pos:,}")
                elif "Range" in merged_headers:
                    del merged_headers["Range"]

                # Use a persistent session for NASA Earthdata OAuth redirect handling
                session = _get_earthdata_session(auth)
                resp = session.get(
                    url,
                    headers={k: v for k, v in merged_headers.items() if k != "Range"
                             or resume_pos > 0},
                    stream=True,
                    timeout=self.timeout,
                    allow_redirects=True,
                )
                # Update url in case of redirect (for logging)
                if resp.url and resp.url != url:
                    url = resp.url

                if resp.status_code == 416:
                    # Range not satisfiable → file already complete
                    if partial.exists() and partial.stat().st_size > 0:
                        partial.rename(dest_path)
                        checksum = self.cache.get_checksum(dest_path)
                        self.cache.register(url, dest_path, checksum)
                        self.dl_log.log(
                            source_label, dest_path.name, url, "SUCCESS",
                            size_bytes=dest_path.stat().st_size,
                            duration_sec=time.monotonic() - start_t,
                            checksum=checksum,
                        )
                        return True

                resp.raise_for_status()

                total = int(resp.headers.get("Content-Length", 0)) + resume_pos
                mode  = "ab" if resume_pos > 0 else "wb"

                with (
                    open(partial, mode) as fh,
                    tqdm(
                        total=total if total > 0 else None,
                        initial=resume_pos,
                        unit="B",
                        unit_scale=True,
                        desc=dest_path.name[:40],
                        leave=False,
                    ) as pbar,
                ):
                    for chunk in resp.iter_content(chunk_size=self.chunk_size):
                        if chunk:
                            fh.write(chunk)
                            pbar.update(len(chunk))

                # ── Success: rename .partial → final ──────────────────────
                partial.rename(dest_path)
                checksum = self.cache.get_checksum(dest_path)
                self.cache.register(url, dest_path, checksum)
                elapsed = time.monotonic() - start_t
                self.dl_log.log(
                    source_label, dest_path.name, url, "SUCCESS",
                    size_bytes=dest_path.stat().st_size,
                    duration_sec=elapsed,
                    checksum=checksum,
                )
                logger.debug(f"OK {dest_path.name} ({dest_path.stat().st_size:,} B, {elapsed:.1f}s)")
                return True

            except (requests.RequestException, OSError) as exc:
                delay = self.retry_delay * (self.retry_backoff ** (attempt - 1))
                logger.warning(
                    f"Attempt {attempt}/{self.retry_attempts} failed for "
                    f"{dest_path.name}: {exc}. Retrying in {delay:.0f}s…"
                )
                time.sleep(delay)

        # All retries exhausted
        self.dl_log.log(source_label, dest_path.name, url, "FAILED",
                        notes=f"Failed after {self.retry_attempts} attempts")
        logger.error(f"FAILED after {self.retry_attempts} attempts: {dest_path.name}")
        return False

    # ------------------------------------------------------------------ #
    # Parallel downloads
    # ------------------------------------------------------------------ #

    def download_parallel(
        self,
        tasks: list,                        # list of (url, dest_path)
        max_workers: Optional[int] = None,
        auth: Optional[tuple] = None,
        headers: Optional[dict] = None,
        source_label: str = "generic",
    ) -> dict:
        """
        Download multiple files in parallel.

        Parameters
        ----------
        tasks       : List of (url, dest_path) tuples.
        max_workers : Thread pool size. Defaults to self.max_workers.
        auth        : HTTP Basic Auth credentials.
        headers     : Extra HTTP headers.
        source_label: Label for download log entries.

        Returns
        -------
        dict  {url: True/False} result per URL.
        """
        workers = max_workers or self.max_workers
        results: dict[str, bool] = {}

        with ThreadPoolExecutor(max_workers=workers) as pool:
            future_map = {}
            for i, (url, dest) in enumerate(tasks):
                if i > 0 and i % workers == 0:
                    time.sleep(self.rate_limit_delay)
                fut = pool.submit(
                    self.download_file, url, dest,
                    headers=headers, auth=auth, source_label=source_label,
                )
                future_map[fut] = url

            for fut in as_completed(future_map):
                url = future_map[fut]
                try:
                    results[url] = fut.result()
                except Exception as exc:
                    logger.error(f"Parallel download error for {url}: {exc}")
                    results[url] = False

        ok  = sum(1 for v in results.values() if v)
        bad = len(results) - ok
        logger.info(f"Parallel download: {ok}/{len(results)} OK, {bad} failed")
        return results

    # ------------------------------------------------------------------ #
    # Convenience
    # ------------------------------------------------------------------ #

    def skip_if_exists(self, dest_path: Path) -> bool:
        """Return True if *dest_path* already exists and is non-empty."""
        p = Path(dest_path)
        return p.exists() and p.stat().st_size > 0
