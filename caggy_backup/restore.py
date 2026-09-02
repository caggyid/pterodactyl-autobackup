"""Restore support with safety mechanisms.

Restore downloads the archive from Google Drive (when it no longer exists
locally), verifies the SHA-256 checksum, then extracts into a target
directory with explicit user confirmation and dry-run support.
"""

from __future__ import annotations

import shutil
import tarfile
from pathlib import Path
from typing import Callable

from . import gdrive
from .compression import resolve_compression_type
from .config import Config
from .database import BackupDatabase, BackupRecord
from .utils import safe_extract_target, sha256_file


class RestoreError(Exception):
    pass


def resolve_backup_artifacts(
    config: Config, db: BackupDatabase, record: BackupRecord
) -> tuple[Path, Path | None, str]:
    """Locate or download the archive + checksum for a record.

    Returns (archive_path, checksum_path_or_None, compression_type).
    """
    compression = record.compression or "zstd"
    compression = resolve_compression_type(compression)
    suffix = ".tar.zst" if compression == "zstd" else ".tar.gz"
    archive_name = f"backup-{suffix}"

    local_dir = Path(record.local_path) if record.local_path else None
    archive_path: Path | None = None
    checksum_path: Path | None = None

    if local_dir and local_dir.exists():
        candidate = local_dir / archive_name
        if candidate.exists():
            archive_path = candidate
            cs_candidate = local_dir / "checksum.sha256"
            if cs_candidate.exists():
                checksum_path = cs_candidate

    if archive_path is None:
        if not record.gdrive_file_id:
            raise RestoreError(
                f"Backup '{record.id}' has no local archive and no Google Drive file id; "
                "it cannot be restored."
            )
        workdir = Path(config.temp_directory) / f"restore-{record.id}"
        workdir.mkdir(parents=True, exist_ok=True)
        creds = gdrive.authenticate(
            Path(config.google_drive.credentials_file),
            Path(config.google_drive.token_file),
        )
        service = gdrive.build_service(creds)
        archive_path = gdrive.download_file(service, record.gdrive_file_id, workdir / archive_name)

        # Try to fetch the matching checksum file from the same folder.
        try:
            file_meta = gdrive.get_file_metadata(service, record.gdrive_file_id)
            parents = file_meta.get("parents", [])
            if parents:
                query = f"'{parents[0]}' in parents and name='checksum.sha256' and trashed=false"
                found = service.files().list(q=query, fields="files(id)", pageSize=1).execute()
                files = found.get("files", [])
                if files:
                    checksum_path = gdrive.download_file(
                        service, files[0]["id"], workdir / "checksum.sha256"
                    )
        except gdrive.GoogleDriveError:
            checksum_path = None

    return archive_path, checksum_path, compression


def verify_archive_checksum(archive_path: Path, checksum_path: Path | None) -> tuple[bool, str]:
    """Verify the archive checksum against the stored checksum file."""
    actual = sha256_file(archive_path)
    expected = ""
    if checksum_path and checksum_path.exists():
        first_line = checksum_path.read_text(encoding="utf-8").strip().splitlines()
        if first_line:
            expected = first_line[0].split()[0].strip().lower()
    if not expected:
        return False, actual
    return expected == actual, actual


def extract_archive(
    archive_path: Path,
    compression: str,
    target_dir: Path,
    strip_shared_root: bool = True,
    progress: Callable[[str], None] | None = None,
) -> int:
    """Safely extract a backup archive into the target directory.

    Rejects path traversal members. Returns the number of extracted
    entries.
    """
    log = progress or (lambda msg: None)
    target_dir = Path(target_dir).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)

    extracted = 0
    with tarfile.open(str(archive_path), mode="r") as tar:
        members = tar.getmembers()
        total = len(members)
        for idx, member in enumerate(members, start=1):
            name = member.name
            # Normalize: strip a shared top-level prefix when present.
            parts = Path(name).parts
            if strip_shared_root and parts and parts[0] in (".", ".."):
                name = str(Path(*parts[1:])) if len(parts) > 1 else ""
            if not name or name in (".", ".."):
                continue
            safe_target = safe_extract_target(target_dir, name)
            _ = safe_target  # validation happened; tarfile handles the actual extract below
            member_path = Path(name)
            if strip_shared_root and len(member_path.parts) > 1:
                candidate_root = member_path.parts[0]
                if candidate_root in ("var", "opt", "srv", "home") and not any(
                    p.name == candidate_root for p in target_dir.iterdir()
                ):
                    # Keep original structure (absolute-style layout inside archive).
                    pass
            member.name = name
            tar.extract(member, path=str(target_dir), filter="data")
            extracted += 1
            if progress and idx % 500 == 0:
                log(f"Extracted {idx}/{total} entries...")
    return extracted


def run_restore(
    config: Config,
    db: BackupDatabase,
    record: BackupRecord,
    target_dir: Path,
    dry_run: bool = False,
    progress: Callable[[str], None] | None = None,
) -> dict:
    """Full restore flow with checksum verification and safety checks."""
    log = progress or (lambda msg: None)
    log(f"Preparing restore of backup '{record.id}'...")

    archive_path, checksum_path, compression = resolve_backup_artifacts(config, db, record)
    log(f"Archive: {archive_path}")

    ok, actual_checksum = verify_archive_checksum(archive_path, checksum_path)
    if ok:
        log("[OK] Checksum verified")
    else:
        if checksum_path:
            raise RestoreError(
                f"Checksum mismatch! Archive may be corrupted.\n"
                f"Expected: {checksum_path.read_text(encoding='utf-8').strip()}\n"
                f"Actual:   {actual_checksum}"
            )
        log(f"WARNING: No checksum file available; computed {actual_checksum}")

    if dry_run:
        log("[DRY-RUN] Extraction skipped.")
        with tarfile.open(str(archive_path), mode="r") as tar:
            count = len(tar.getmembers())
        return {
            "dry_run": True,
            "archive": str(archive_path),
            "checksum_ok": ok,
            "entries": count,
            "target": str(target_dir),
        }

    count = extract_archive(archive_path, compression, target_dir, progress=log)
    log(f"[OK] Restored {count} entries into {target_dir}")
    return {
        "dry_run": False,
        "archive": str(archive_path),
        "checksum_ok": ok,
        "entries": count,
        "target": str(target_dir),
    }


def cleanup_restore_temp(config: Config, record_id: str) -> None:
    workdir = Path(config.temp_directory) / f"restore-{record_id}"
    if workdir.exists():
        shutil.rmtree(workdir, ignore_errors=True)
