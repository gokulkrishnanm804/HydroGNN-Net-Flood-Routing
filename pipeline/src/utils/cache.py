"""
HydroGNN-Net Research Pipeline — Exception Classes & Cache Manager

Classes
-------
DataSourceUnavailable   Raised when a required external data source cannot be accessed.
PipelineError           Raised for general pipeline execution errors.
CacheManager            MD5-checksum-based file cache for download deduplication.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Custom Exceptions
# ---------------------------------------------------------------------------

class DataSourceUnavailable(Exception):
    """
    Raised when a required external data source is unavailable.

    This may be due to:
    - Missing credentials (NASA Earthdata, Copernicus CDS)
    - No manually exported data files placed in the expected directory
    - Network failure after all retries exhausted

    The message should always include actionable instructions for the user.
    """


class PipelineError(Exception):
    """General pipeline execution error."""


# ---------------------------------------------------------------------------
# Cache Manager
# ---------------------------------------------------------------------------

class CacheManager:
    """
    MD5 checksum-based cache for downloaded files.

    Maintains a JSON registry mapping (url → checksum) so that already-
    downloaded files are not re-downloaded on subsequent runs.

    Parameters
    ----------
    cache_dir : Path
        Directory used to store cache_registry.json.
    """

    REGISTRY_FILENAME = "cache_registry.json"

    def __init__(self, cache_dir: Path) -> None:
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.registry_path = self.cache_dir / self.REGISTRY_FILENAME
        self._registry: dict[str, str] = self.load_registry()

    # ------------------------------------------------------------------ #
    # Registry I/O
    # ------------------------------------------------------------------ #

    def load_registry(self) -> dict[str, str]:
        """Load the URL→checksum registry from disk."""
        if self.registry_path.exists():
            try:
                with open(self.registry_path, "r", encoding="utf-8") as fh:
                    return json.load(fh)
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def save_registry(self) -> None:
        """Persist the in-memory registry to disk."""
        with open(self.registry_path, "w", encoding="utf-8") as fh:
            json.dump(self._registry, fh, indent=2)

    # ------------------------------------------------------------------ #
    # Checksum
    # ------------------------------------------------------------------ #

    def get_checksum(self, filepath: Path, block_size: int = 65536) -> str:
        """
        Compute MD5 checksum of a file.

        Parameters
        ----------
        filepath   : Path to the file.
        block_size : Read block size in bytes.

        Returns
        -------
        Hex-encoded MD5 digest string.
        """
        md5 = hashlib.md5()
        with open(filepath, "rb") as fh:
            for block in iter(lambda: fh.read(block_size), b""):
                md5.update(block)
        return md5.hexdigest()

    # ------------------------------------------------------------------ #
    # Cache Queries
    # ------------------------------------------------------------------ #

    def is_cached(self, url: str, dest_path: Path) -> bool:
        """
        Return True if *dest_path* exists and its checksum matches the registry.

        A file that exists but has no registry entry (e.g., placed manually) is
        treated as valid without checksum verification.

        Parameters
        ----------
        url       : The URL the file was downloaded from.
        dest_path : Local path of the downloaded file.
        """
        dest_path = Path(dest_path)
        if not dest_path.exists() or dest_path.stat().st_size == 0:
            return False
        stored = self._registry.get(url)
        if stored is None:
            # File exists but was not registered; treat as fresh (no re-download)
            return True
        actual = self.get_checksum(dest_path)
        return actual == stored

    def register(self, url: str, dest_path: Path, checksum: Optional[str] = None) -> None:
        """
        Register a successfully downloaded file in the cache.

        Parameters
        ----------
        url      : Source URL.
        dest_path: Local file path.
        checksum : Pre-computed MD5; if None it is computed here.
        """
        if checksum is None:
            checksum = self.get_checksum(Path(dest_path))
        self._registry[url] = checksum
        self.save_registry()

    # ------------------------------------------------------------------ #
    # Partial Download Support
    # ------------------------------------------------------------------ #

    @staticmethod
    def partial_path(dest_path: Path) -> Path:
        """Return the .partial sibling path for a destination file."""
        return Path(str(dest_path) + ".partial")

    def is_partial(self, dest_path: Path) -> bool:
        """Return True if a .partial temp file exists (interrupted download)."""
        return self.partial_path(dest_path).exists()

    def get_partial_size(self, dest_path: Path) -> int:
        """Return the number of bytes already downloaded in the .partial file."""
        partial = self.partial_path(dest_path)
        return partial.stat().st_size if partial.exists() else 0
