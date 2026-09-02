"""Backup engine: create archive, checksum, metadata, upload to Drive."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, List

from . import gdrive
from .compression import (
    CompressionError,
    ZstdUnavailableError,
    archive_suffix,
    create_archive,
    resolve_compression_type,
)
from .config import Config
from .database import BackupDatabase, BackupRecord, STATUS_FAILED, STATUS_SUCCESS
from .utils import (
    EXIT_AUTH,
    EXIT_BACKUP,
    EXIT_UPLOAD,
    ensure_dir,
    get_hostname,
    human_size,
    make_backup_id,
    check_disk_space,
    sha256_file,
    utc_timestamp,
)


class BackupError(Exception):
    def __init__(self, message: str, exit_code: int = EXIT_BACKUP):
        super().__init__(message)
        self.exit_code = exit_code


@dataclass
class BackupResult:
    backup_id: str
    archive_path: Path
    archive_size: int
    checksum: str
    compression: str
    duration_sec: float
    gdrive_file_id: str | None = None
    uploaded: bool = False
    servers: List[str] = field(default_factory=list)


def discover_servers(sources: list[Path]) -> list[str]:
    """List Pterodactyl server volumes (directory names) under sources."""
    servers: List[str] = []
    for source in sources:
        if source.is_dir():
            for child in sorted(source.iterdir()):
                if child.is_dir() and not child.name.startswith("."):
                    servers.append(child.name)
    return servers


def estimate_source_size(sources: list[Path], excludes: list[str] | None = None) -> int:
    """Best-effort estimate of the total source size in bytes."""
    from .compression import _matches_exclude
    import os

    total = 0
    for source in sources:
        if not source.is_dir():
            continue
        for root, _dirs, files in os.walk(source):
            for name in files:
                full = Path(root) / name
                rel = str(full.relative_to(source))
                if excludes and _matches_exclude(rel, excludes):
                    continue
                try:
                    total += full.stat().st_size
                except OSError:
                    continue
    return total


def run_backup(
    config: Config,
    backup_id: str | None = None,
    selected_servers: list[str] | None = None,
    upload: bool = True,
    progress: Callable[[str], None] | None = None,
    db: BackupDatabase | None = None,
) -> BackupResult:
    """Execute a full backup run: compress, checksum, upload, record.

    Raises BackupError with a matching exit code on failure.
    """
    log = progress or (lambda msg: None)
    backup_id = backup_id or make_backup_id()
    hostname = get_hostname()
    started = time.monotonic()
    archive_suffix_used = archive_suffix(resolve_compression_type(config.compression.type))
    temp_dir = ensure_dir(config.temp_directory / backup_id)

    own_db = db is None
    if own_db:
        db = BackupDatabase()

    servers = selected_servers or discover_servers(config.sources)
    servers_display = ",".join(servers) if servers else "(full volume)"
    record = BackupRecord(
        id=backup_id,
        created_at=utc_timestamp(),
        hostname=hostname,
        servers=servers_display,
        size=0,
        checksum="",
        gdrive_file_id="",
        status="PENDING",
        duration_sec=0.0,
        error_message="",
        local_path="",
        compression=config.compression.type,
    )
    assert db is not None
    try:
        db.insert(record)
    except Exception as exc:  # database must not block backup runs silently
        log(f"WARNING: could not write history record: {exc}")

    archive_path = temp_dir / f"backup-{archive_suffix_used}"
    checksum_path = temp_dir / "checksum.sha256"
    metadata_path = temp_dir / "metadata.json"

    try:
        # 1. Disk space check ------------------------------------------------
        log("Checking disk space...")
        source_paths = _resolve_server_paths(config.sources, servers, selected_servers is not None)
        required = estimate_source_size(source_paths, config.exclude)
        # Archives rarely exceed source size; still require headroom for it.
        if not check_disk_space(config.temp_directory, required + 512 * 1024 * 1024):
            raise BackupError(
                "Not enough disk space in temporary directory "
                f"{config.temp_directory} (required ~{human_size(required)}).",
                EXIT_BACKUP,
            )
        log(f"[OK] Enough disk space (required ~{human_size(required)})")

        # 2. Compress ---------------------------------------------------------
        log("Compressing data...")
        try:
            create_archive(
                sources=source_paths,
                output_file=archive_path,
                compression=resolve_compression_type(config.compression.type),
                level=config.compression.level,
                excludes=config.exclude,
            )
        except ZstdUnavailableError as exc:
            raise BackupError(str(exc), EXIT_BACKUP) from exc
        except CompressionError as exc:
            raise BackupError(str(exc), EXIT_BACKUP) from exc

        archive_size = archive_path.stat().st_size
        log(f"[OK] Archive created: {archive_path.name} ({human_size(archive_size)})")

        # 3. Checksum + metadata ---------------------------------------------
        log("Computing SHA-256 checksum...")
        checksum = sha256_file(archive_path)
        checksum_path.write_text(f"{checksum}  {archive_path.name}\n", encoding="utf-8")

        metadata = {
            "project": "CaggyID Pterodactyl Backup",
            "version": "1.0.0",
            "created_at": utc_timestamp(),
            "backup_id": backup_id,
            "hostname": hostname,
            "backup_size": archive_size,
            "compression": resolve_compression_type(config.compression.type),
            "checksum": checksum,
            "servers": servers,
            "sources": [str(p) for p in source_paths],
        }
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

        db.update(
            backup_id,
            size=archive_size,
            checksum=checksum,
            status="PENDING",
            local_path=str(temp_dir),
            compression=resolve_compression_type(config.compression.type),
        )

        # 4. Upload ------------------------------------------------------------
        gdrive_file_id: str | None = None
        if upload:
            log("Uploading to Google Drive...")
            creds = gdrive.authenticate(
                Path(config.google_drive.credentials_file),
                Path(config.google_drive.token_file),
            )
            service = gdrive.build_service(creds)
            root_folder_id = gdrive.get_folder_path(
                service, [config.google_drive.folder_name, hostname, str(datetime.now().year), f"{datetime.now().month:02d}"]
            )
            last_pct = [-1]

            def upload_progress(fraction: float) -> None:
                pct = int(fraction * 100)
                if pct >= last_pct[0] + 10:
                    last_pct[0] = pct
                    log(f"Upload progress: {pct}%")

            try:
                gdrive_file_id = gdrive.upload_file(
                    service, archive_path, archive_path.name, root_folder_id,
                    progress_callback=upload_progress,
                )
                gdrive.upload_file(service, checksum_path, checksum_path.name, root_folder_id)
                gdrive.upload_file(service, metadata_path, metadata_path.name, root_folder_id)
            except gdrive.GoogleDriveError as exc:
                raise BackupError(str(exc), EXIT_UPLOAD) from exc
            log("[OK] Upload complete")

        duration = time.monotonic() - started
        db.update(
            backup_id,
            gdrive_file_id=gdrive_file_id or "",
            status=STATUS_SUCCESS if (upload and gdrive_file_id) or not upload else STATUS_FAILED,
            duration_sec=round(duration, 2),
        )

        return BackupResult(
            backup_id=backup_id,
            archive_path=archive_path,
            archive_size=archive_size,
            checksum=checksum,
            compression=resolve_compression_type(config.compression.type),
            duration_sec=duration,
            gdrive_file_id=gdrive_file_id,
            uploaded=gdrive_file_id is not None,
            servers=servers,
        )

    except BackupError as exc:
        duration = time.monotonic() - started
        try:
            db.update(backup_id, status=STATUS_FAILED, error_message=str(exc), duration_sec=round(duration, 2))
        except Exception:
            pass
        _cleanup(temp_dir, keep_on_error=True)
        raise
    except gdrive.GoogleDriveAuthError as exc:
        duration = time.monotonic() - started
        try:
            db.update(backup_id, status=STATUS_FAILED, error_message=str(exc), duration_sec=round(duration, 2))
        except Exception:
            pass
        _cleanup(temp_dir, keep_on_error=True)
        raise BackupError(str(exc), EXIT_AUTH) from exc
    finally:
        if own_db:
            db.close()


def _resolve_server_paths(sources: list[Path], servers: list[str], selective: bool) -> list[Path]:
    """Map selected server names onto actual volume paths."""
    if not selective:
        return [Path(p) for p in sources]
    resolved: list[Path] = []
    for source in sources:
        for server in servers:
            candidate = source / server
            if candidate.is_dir():
                resolved.append(candidate)
    if not resolved:
        raise BackupError(
            f"None of the selected servers were found under the configured sources: {', '.join(servers)}",
            EXIT_BACKUP,
        )
    return resolved


def _cleanup(temp_dir: Path, keep_on_error: bool = False) -> None:
    """Remove the temp backup directory; keep artifacts when a retry may help."""
    _ = keep_on_error
    import shutil

    shutil.rmtree(temp_dir, ignore_errors=True)
