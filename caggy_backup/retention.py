"""Retention policy: prune old backups locally and on Google Drive.

Implements a grandfather-father-son style policy on top of the SQLite
history: keep_last, keep_daily, keep_weekly, keep_monthly. Local temp
artifacts are removed along with their Drive copies.
"""

from __future__ import annotations

import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Set

from . import gdrive
from .config import Config, RetentionConfig
from .database import BackupDatabase, BackupRecord, parse_backup_created_at


@dataclass
class CleanupPlan:
    keep: List[BackupRecord] = field(default_factory=list)
    delete: List[BackupRecord] = field(default_factory=list)


class RetentionError(Exception):
    pass


def compute_retention(records: List[BackupRecord], policy: RetentionConfig) -> CleanupPlan:
    """Compute which successful backups to keep or delete.

    The most recent ``keep_last`` backups are always kept. Older backups
    are grouped per calendar day/week/month and the newest of each group
    is kept up to the configured limits (most recent groups win).
    """
    successful = [r for r in records if r.status == "SUCCESS"]
    successful.sort(key=lambda r: parse_backup_created_at(r), reverse=True)

    keep_ids: Set[str] = set()

    # keep_last: always keep the newest N.
    for record in successful[: max(policy.keep_last, 0)]:
        keep_ids.add(record.id)

    seen_daily: Set[str] = set()
    seen_weekly: Set[str] = set()
    seen_monthly: Set[str] = set()
    daily_count = weekly_count = monthly_count = 0

    for record in successful:
        dt = parse_backup_created_at(record)
        if record.id in keep_ids:
            continue

        day_key = dt.strftime("%Y-%m-%d")
        week_key = f"{dt.isocalendar().year}-W{dt.isocalendar().week:02d}"
        month_key = dt.strftime("%Y-%m")

        if policy.keep_daily > 0 and day_key not in seen_daily and daily_count < policy.keep_daily:
            seen_daily.add(day_key)
            daily_count += 1
            keep_ids.add(record.id)
            continue

        if policy.keep_weekly > 0 and week_key not in seen_weekly and weekly_count < policy.keep_weekly:
            seen_weekly.add(week_key)
            weekly_count += 1
            keep_ids.add(record.id)
            continue

        if policy.keep_monthly > 0 and month_key not in seen_monthly and monthly_count < policy.keep_monthly:
            seen_monthly.add(month_key)
            monthly_count += 1
            keep_ids.add(record.id)
            continue

    plan = CleanupPlan(
        keep=[r for r in successful if r.id in keep_ids],
        delete=[r for r in successful if r.id not in keep_ids],
    )
    return plan


def delete_local_backup(record: BackupRecord) -> bool:
    """Remove the local temp artifacts of a backup, if present."""
    if not record.local_path:
        return False
    local_dir = Path(record.local_path)
    existed = local_dir.exists()
    if existed and str(local_dir).startswith(("/tmp/", "/var/tmp/")):
        shutil.rmtree(local_dir, ignore_errors=True)
    elif existed:
        # Only delete known artifact files, not arbitrary directories.
        for name in ("backup.tar.zst", "backup.tar.gz", "metadata.json", "checksum.sha256"):
            target = local_dir / name
            try:
                target.unlink()
            except OSError:
                pass
    return existed


def delete_drive_backup(config: Config, record: BackupRecord, progress: Callable[[str], None] | None = None) -> bool:
    """Delete the Drive copy of a backup by matching the archive file id.

    Sibling checksum/metadata files are matched by upload order in the
    same folder and removed as well.
    """
    log = progress or (lambda msg: None)
    if not record.gdrive_file_id:
        return False
    try:
        creds = gdrive.authenticate(
            Path(config.google_drive.credentials_file),
            Path(config.google_drive.token_file),
        )
        service = gdrive.build_service(creds)
        meta = gdrive.get_file_metadata(service, record.gdrive_file_id)
        parents = meta.get("parents", [])
        gdrive.delete_file(service, record.gdrive_file_id)
        if parents:
            for sibling in ("checksum.sha256", "metadata.json"):
                query = f"'{parents[0]}' in parents and name='{sibling}' and trashed=false"
                found = service.files().list(q=query, fields="files(id)", pageSize=5).execute()
                for f in found.get("files", []):
                    try:
                        gdrive.delete_file(service, f["id"])
                    except gdrive.GoogleDriveError as exc:
                        log(f"WARNING: could not delete {sibling}: {exc}")
                        time.sleep(1)
        return True
    except gdrive.GoogleDriveError as exc:
        log(f"WARNING: failed to delete Drive backup {record.id}: {exc}")
        return False


def run_cleanup(
    config: Config,
    db: BackupDatabase,
    dry_run: bool = False,
    delete_drive: bool = True,
    progress: Callable[[str], None] | None = None,
) -> CleanupPlan:
    """Compute and (optionally) execute the retention cleanup."""
    log = progress or (lambda msg: None)
    plan = compute_retention(db.list_all(), config.retention)

    if not config.retention.enabled:
        log("Retention is disabled in configuration; nothing to clean.")
        return CleanupPlan(keep=plan.keep, delete=[])

    if dry_run:
        return plan

    for record in plan.delete:
        log(f"Removing backup {record.id}...")
        if delete_local_backup(record):
            log(f"  [OK] Local artifacts removed")
        if delete_drive:
            if delete_drive_backup(config, record, log):
                log("  [OK] Google Drive copy removed")
        db.delete(record.id)

    return plan
