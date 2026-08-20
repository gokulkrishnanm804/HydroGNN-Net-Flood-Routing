"""
HydroGNN-Net Research Pipeline — Logging Utilities

Provides:
- get_logger()      Structured console + rotating-file logger.
- log_separator()   Visual section dividers in the log output.
- DownloadLogger    Appends structured CSV rows to download_log.csv.
"""
from __future__ import annotations

import csv
import logging
import sys
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

# Global logger cache to avoid duplicate handlers on re-import
_LOGGERS: dict[str, logging.Logger] = {}


# ─────────────────────────────────────────────────────────────────────────────
# Public helpers
# ─────────────────────────────────────────────────────────────────────────────

def get_logger(
    name: str,
    log_dir: Optional[Path] = None,
    level: int = logging.INFO,
) -> logging.Logger:
    """
    Create or retrieve a named logger with console + optional file handlers.

    Parameters
    ----------
    name    : Logger name (typically ``__name__`` of the calling module).
    log_dir : If given, a rotating file handler is added at DEBUG level.
    level   : Console handler logging level (default INFO).

    Returns
    -------
    logging.Logger
    """
    if name in _LOGGERS:
        return _LOGGERS[name]

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    # ── Console handler ───────────────────────────────────────────────────
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(level)
    ch.setFormatter(_ColourFormatter())
    logger.addHandler(ch)

    # ── File handler (rotating, DEBUG) ────────────────────────────────────
    if log_dir is not None:
        log_dir = Path(log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        safe_name = name.replace(".", "_").replace("/", "_")
        fh = RotatingFileHandler(
            log_dir / f"{safe_name}.log",
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
            encoding="utf-8",
        )
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(
            logging.Formatter(
                "%(asctime)s | %(name)s | %(levelname)-8s | %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S",
            )
        )
        logger.addHandler(fh)

    _LOGGERS[name] = logger
    return logger


def log_separator(logger: logging.Logger, title: str, width: int = 72) -> None:
    """Log a prominent section divider."""
    bar = "=" * width
    logger.info(bar)
    logger.info(f"  {title}")
    logger.info(bar)


# ─────────────────────────────────────────────────────────────────────────────
# Internal: colour formatter
# ─────────────────────────────────────────────────────────────────────────────

class _ColourFormatter(logging.Formatter):
    """Console formatter with ANSI colour coding per log level."""

    _GREY      = "\x1b[38;5;245m"
    _CYAN      = "\x1b[36m"
    _GREEN     = "\x1b[32m"
    _YELLOW    = "\x1b[33m"
    _RED       = "\x1b[31m"
    _BOLD_RED  = "\x1b[1;31m"
    _RESET     = "\x1b[0m"

    _COLOURS = {
        logging.DEBUG:    _GREY,
        logging.INFO:     _GREEN,
        logging.WARNING:  _YELLOW,
        logging.ERROR:    _RED,
        logging.CRITICAL: _BOLD_RED,
    }

    _FMT = "%(asctime)s | %(name)-25s | {c}%(levelname)-8s{r} | %(message)s"

    def format(self, record: logging.LogRecord) -> str:  # noqa: A003
        colour = self._COLOURS.get(record.levelno, self._RESET)
        fmt = self._FMT.format(c=colour, r=self._RESET)
        return logging.Formatter(fmt, datefmt="%H:%M:%S").format(record)


# ─────────────────────────────────────────────────────────────────────────────
# Download CSV Logger
# ─────────────────────────────────────────────────────────────────────────────

class DownloadLogger:
    """
    Appends one CSV row per download operation to *download_log.csv*.

    Columns
    -------
    timestamp, source, filename, url, status, size_bytes, duration_sec,
    checksum, notes
    """

    COLUMNS = [
        "timestamp", "source", "filename", "url", "status",
        "size_bytes", "duration_sec", "checksum", "notes",
    ]

    def __init__(self, log_path: Path) -> None:
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.log_path.exists():
            with open(self.log_path, "w", newline="", encoding="utf-8") as fh:
                csv.DictWriter(fh, fieldnames=self.COLUMNS).writeheader()

    # ------------------------------------------------------------------ #

    def log(
        self,
        source: str,
        filename: str,
        url: str,
        status: str,          # SUCCESS | FAILED | SKIPPED | PARTIAL
        size_bytes: int = 0,
        duration_sec: float = 0.0,
        checksum: str = "",
        notes: str = "",
    ) -> None:
        """Append a single download record."""
        row = {
            "timestamp":    datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "source":       source,
            "filename":     filename,
            "url":          url,
            "status":       status,
            "size_bytes":   size_bytes,
            "duration_sec": round(duration_sec, 3),
            "checksum":     checksum,
            "notes":        notes,
        }
        with open(self.log_path, "a", newline="", encoding="utf-8") as fh:
            csv.DictWriter(fh, fieldnames=self.COLUMNS).writerow(row)

    def get_summary(self) -> dict:
        """Return aggregate statistics from the download log."""
        stats: dict = {"total": 0, "success": 0, "failed": 0,
                       "skipped": 0, "total_bytes": 0}
        if not self.log_path.exists():
            return stats
        with open(self.log_path, "r", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                stats["total"] += 1
                st = row.get("status", "").upper()
                if st == "SUCCESS":
                    stats["success"] += 1
                    stats["total_bytes"] += int(row.get("size_bytes") or 0)
                elif st == "FAILED":
                    stats["failed"] += 1
                elif st == "SKIPPED":
                    stats["skipped"] += 1
        return stats
