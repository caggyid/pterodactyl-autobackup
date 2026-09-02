"""SQLite-backed backup history storage.

The database lives by default at ``~/.caggy-backup/database.db`` and stores
one row per backup attempt with id, timestamp, hostname, servers, size,
checksum, Google Drive file id, status, duration, and error message.
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

STATUS_PENDING = "PENDING"
STATUS_SUCCESS = "SUCCESS"
STATUS_FAILED = "FAILED"

SCHEMA = """
CREATE TABLE IF NOT EXISTS backups (
    id            TEXT PRIMARY KEY,
    created_at    TEXT NOT NULL,
    hostname      TEXT NOT NULL,
    servers       TEXT NOT NULL DEFAULT '',
    size          INTEGER NOT NULL DEFAULT 0,
    checksum      TEXT NOT NULL DEFAULT '',
    gdrive_file_id TEXT NOT NULL DEFAULT '',
    status        TEXT NOT NULL DEFAULT 'PENDING',
    duration_sec  REAL NOT NULL DEFAULT 0,
    error_message TEXT NOT NULL DEFAULT '',
    local_path    TEXT NOT NULL DEFAULT '',
    compression   TEXT NOT NULL DEFAULT ''
);
"""


def default_db_path() -> Path:
    return Path(os.path.expanduser("~/.caggy-backup/database.db"))


@dataclass
class BackupRecord:
    id: str
    created_at: str
    hostname: str
    servers: str
    size: int
    checksum: str
    gdrive_file_id: str
    status: str
    duration_sec: float
    error_message: str
    local_path: str
    compression: str


class BackupDatabase:
    def __init__(self, db_path: Path | None = None):
        self.db_path = Path(db_path) if db_path else default_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        if os.name == "posix":
            os.chmod(self.db_path.parent, 0o700)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        try:
            self._conn.close()
        except sqlite3.Error:
            pass

    # ------------------------------------------------------------------
    def insert(self, record: BackupRecord) -> None:
        self._conn.execute(
            """INSERT INTO backups
               (id, created_at, hostname, servers, size, checksum, gdrive_file_id,
                status, duration_sec, error_message, local_path, compression)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record.id,
                record.created_at,
                record.hostname,
                record.servers,
                record.size,
                record.checksum,
                record.gdrive_file_id,
                record.status,
                record.duration_sec,
                record.error_message,
                record.local_path,
                record.compression,
            ),
        )
        self._conn.commit()

    def update(self, backup_id: str, **fields: object) -> None:
        allowed = (
            "size", "checksum", "gdrive_file_id", "status",
            "duration_sec", "error_message", "local_path", "servers",
        )
        keys = [k for k in fields if k in allowed]
        if not keys:
            return
        assignments = ", ".join(f"{k} = ?" for k in keys)
        values = [fields[k] for k in keys]
        values.append(backup_id)
        self._conn.execute(f"UPDATE backups SET {assignments} WHERE id = ?", values)
        self._conn.commit()

    def get(self, backup_id: str) -> BackupRecord | None:
        row = self._conn.execute(
            "SELECT * FROM backups WHERE id = ?", (backup_id,)
        ).fetchone()
        return self._row_to_record(row) if row else None

    def list_all(self, limit: int | None = None) -> list[BackupRecord]:
        query = "SELECT * FROM backups ORDER BY created_at DESC"
        if limit:
            query += f" LIMIT {int(limit)}"
        rows = self._conn.execute(query).fetchall()
        return [self._row_to_record(r) for r in rows]

    def list_success(self, hostname: str | None = None) -> list[BackupRecord]:
        if hostname:
            rows = self._conn.execute(
                "SELECT * FROM backups WHERE status = ? AND hostname = ? ORDER BY created_at DESC",
                (STATUS_SUCCESS, hostname),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM backups WHERE status = ? ORDER BY created_at DESC",
                (STATUS_SUCCESS,),
            ).fetchall()
        return [self._row_to_record(r) for r in rows]

    def delete(self, backup_id: str) -> None:
        self._conn.execute("DELETE FROM backups WHERE id = ?", (backup_id,))
        self._conn.commit()

    # ------------------------------------------------------------------
    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> BackupRecord:
        return BackupRecord(
            id=row["id"],
            created_at=row["created_at"],
            hostname=row["hostname"],
            servers=row["servers"],
            size=row["size"],
            checksum=row["checksum"],
            gdrive_file_id=row["gdrive_file_id"],
            status=row["status"],
            duration_sec=row["duration_sec"],
            error_message=row["error_message"],
            local_path=row["local_path"],
            compression=row["compression"],
        )


def parse_backup_created_at(record: BackupRecord) -> datetime:
    """Parse the created_at field of a record (ISO or raw backup id)."""
    raw = record.created_at
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d_%H%M%S"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    # Fallback: try to parse from the backup id.
    try:
        return datetime.strptime(record.id, "%Y-%m-%d_%H%M%S")
    except ValueError:
        return datetime.now()
