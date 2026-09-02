"""Utility helpers shared across the CaggyID backup tool."""

from __future__ import annotations

import hashlib
import os
import platform
import shutil
import socket
import tempfile
from pathlib import Path
from typing import Iterator

EXIT_OK = 0
EXIT_GENERAL = 1
EXIT_CONFIG = 2
EXIT_AUTH = 3
EXIT_BACKUP = 4
EXIT_UPLOAD = 5

CHUNK_SIZE = 1024 * 1024  # 1 MiB


def human_size(num_bytes: int | float) -> str:
    """Format a byte count into a human readable string."""
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} TB"


def sha256_file(path: Path) -> str:
    """Compute the SHA-256 checksum of a file by streaming it in chunks."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def get_hostname() -> str:
    """Return a filesystem/Drive-safe hostname identifier."""
    name = socket.gethostname() or "unknown-host"
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in name)


def disk_free_space(path: Path) -> int:
    """Return free bytes available on the filesystem containing *path*."""
    return shutil.disk_usage(str(path)).free


def disk_total_space(path: Path) -> int:
    return shutil.disk_usage(str(path)).total


def check_disk_space(path: Path, required_bytes: int) -> bool:
    """Return True when *path* has at least *required_bytes* free."""
    return disk_free_space(path) >= required_bytes


def validate_source_path(raw: str) -> Path:
    """Validate a user provided backup source path.

    Raises ValueError when the path is empty, relative-only traversal,
    nonexistent, or not a directory.
    """
    value = raw.strip()
    if not value:
        raise ValueError("Source path cannot be empty.")
    path = Path(os.path.abspath(os.path.expanduser(value)))
    if not path.exists():
        raise ValueError(f"Source path does not exist: {path}")
    if not path.is_dir():
        raise ValueError(f"Source path is not a directory: {path}")
    return path


def validate_output_path(raw: str, allow_missing: bool = True) -> Path:
    """Validate and normalize an output/destination path."""
    path = Path(os.path.abspath(os.path.expanduser(raw.strip())))
    if path.exists() and not path.is_dir():
        raise ValueError(f"Path exists and is not a directory: {path}")
    if not path.exists() and not allow_missing:
        raise ValueError(f"Directory does not exist: {path}")
    return path


def is_within_directory(base: Path, target: Path) -> bool:
    """Safely check whether *target* resolves inside *base*."""
    try:
        base_resolved = base.resolve()
        target_resolved = target.resolve()
    except OSError:
        return False
    return str(target_resolved).startswith(str(base_resolved) + os.sep)


def safe_extract_target(base: Path, member_name: str) -> Path:
    """Resolve a tar member path and reject path traversal attempts."""
    base = base.resolve()
    target = (base / member_name).resolve()
    if not str(target).startswith(str(base) + os.sep) and target != base:
        raise ValueError(f"Unsafe path in archive detected: {member_name}")
    return target


def ensure_dir(path: Path, mode: int | None = None) -> Path:
    """Create a directory (including parents) with optional permissions."""
    path.mkdir(parents=True, exist_ok=True)
    if mode is not None and os.name == "posix":
        os.chmod(path, mode)
    return path


def utc_timestamp() -> str:
    """Return a UTC timestamp string used in metadata and logs."""
    import datetime

    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def make_backup_id() -> str:
    """Generate a backup ID such as ``2026-09-02_203000`` (local time)."""
    import datetime

    return datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")


def which_tool(name: str) -> str | None:
    """Locate an external compression binary, or None when unavailable."""
    return shutil.which(name)


def platform_info() -> str:
    return f"{platform.system()} {platform.release()} ({platform.machine()})"


def iter_file_chunks(path: Path, chunk: int = CHUNK_SIZE) -> Iterator[bytes]:
    with open(path, "rb") as handle:
        while True:
            data = handle.read(chunk)
            if not data:
                break
            yield data


def atomic_write_text(path: Path, content: str) -> None:
    """Write text to a file atomically (write temp, then rename)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
