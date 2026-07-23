"""Persistent storage for completed quality-check runs (SQLite-backed).

Each row is one finished QC run: when it happened, which material, and the
resulting mean/std force. This is local-machine data, not synced anywhere —
unlike the material property database in this same package, which is pulled
from the shared hepic_database releases. HEPiC (desktop) and hepic_device
(embedded backend) each keep their own history file on their own machine, but
share this implementation since hepic_device already depends on the HEPiC
package directly.
"""

from __future__ import annotations

import os
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional


def get_qc_history_db_path() -> Path:
    """Per-user writable path the QC history database lives in."""
    override = os.environ.get("HEPIC_QC_HISTORY_DB")
    if override:
        path = Path(override)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        root = Path(base) / "HEPiC"
    elif sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support" / "HEPiC"
    else:
        xdg_data_home = os.environ.get("XDG_DATA_HOME")
        root = (Path(xdg_data_home) if xdg_data_home else Path.home() / ".local" / "share") / "hepic"

    root.mkdir(parents=True, exist_ok=True)
    return root / "qc_history.sqlite3"


@dataclass
class QcHistoryRecord:
    id: int
    timestamp: str  # ISO 8601, e.g. "2026-07-23T14:32:07"
    family: Optional[str]
    pi_code: Optional[str]
    mean_force: Optional[float]
    std_force: Optional[float]


class QcHistoryStore:
    """Thin sqlite3 wrapper. Opens a short-lived connection per call rather
    than holding one open — writes are infrequent (at most one per finished
    QC run), so there's no contention to optimize for."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or get_qc_history_db_path()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS qc_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    family TEXT,
                    pi_code TEXT,
                    mean_force REAL,
                    std_force REAL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_qc_history_timestamp ON qc_history(timestamp)"
            )

    def add(
        self,
        *,
        family: Optional[str],
        pi_code: Optional[str],
        mean_force: Optional[float],
        std_force: Optional[float],
        timestamp: Optional[str] = None,
    ) -> QcHistoryRecord:
        ts = timestamp or datetime.now().isoformat(timespec="seconds")
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO qc_history (timestamp, family, pi_code, mean_force, std_force) "
                "VALUES (?, ?, ?, ?, ?)",
                (ts, family, pi_code, mean_force, std_force),
            )
            row_id = cur.lastrowid
        return QcHistoryRecord(row_id, ts, family, pi_code, mean_force, std_force)

    def list_recent(self, limit: int = 200) -> list[QcHistoryRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, timestamp, family, pi_code, mean_force, std_force "
                "FROM qc_history ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [QcHistoryRecord(**dict(row)) for row in rows]


_default_store: Optional[QcHistoryStore] = None


def get_qc_history_store() -> QcHistoryStore:
    global _default_store
    if _default_store is None:
        _default_store = QcHistoryStore()
    return _default_store
