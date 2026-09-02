"""Compression support: tar streaming with zstd or gzip.

zstd is used through the system ``zstd`` binary via safe subprocess calls
(no shell interpolation). When zstd is not available, the tool falls back
to gzip through Python's stdlib so backups keep working everywhere.
"""

from __future__ import annotations

import gzip
import io
import os
import subprocess
import tarfile
from pathlib import Path

from .config import Config
from .utils import which_tool

ZSTD_SUFFIX = ".tar.zst"
GZIP_SUFFIX = ".tar.gz"


class CompressionError(Exception):
    pass


class ZstdUnavailableError(CompressionError):
    pass


def archive_suffix(compression_type: str) -> str:
    return ZSTD_SUFFIX if compression_type == "zstd" else GZIP_SUFFIX


def zstd_available() -> bool:
    return which_tool("zstd") is not None


def resolve_compression_type(requested: str) -> str:
    """Return the compression actually used, falling back to gzip."""
    if requested == "zstd" and not zstd_available():
        return "gzip"
    return requested


def _matches_exclude(rel_path: str, excludes: list[str]) -> bool:
    rel_norm = rel_path.replace("\\", "/")
    for pattern in excludes:
        pattern_norm = pattern.strip().replace("\\", "/").strip("/")
        if not pattern_norm:
            continue
        parts = rel_norm.split("/")
        if pattern_norm in parts:
            return True
        if rel_norm == pattern_norm:
            return True
        if rel_norm.startswith(pattern_norm + "/"):
            return True
        # simple glob-style suffix match e.g. *.log
        if pattern_norm.startswith("*") and rel_norm.endswith(pattern_norm[1:]):
            return True
    return False


def create_archive(
    sources: list[Path],
    output_file: Path,
    compression: str,
    level: int,
    excludes: list[str] | None = None,
    progress_callback=None,
) -> Path:
    """Create a compressed tar archive from the given source directories.

    The tar is streamed into the compression process so peak memory stays
    low even for very large Pterodactyl volumes.
    """
    excludes = excludes or []
    output_file.parent.mkdir(parents=True, exist_ok=True)

    if compression == "zstd":
        if not zstd_available():
            raise ZstdUnavailableError(
                "The 'zstd' binary is required for zstd compression but was not found. "
                "Install it (e.g. 'apt install zstd') or set compression type to 'gzip'."
            )
        cmd = ["zstd", f"-{min(max(level, 1), 19)}", "-T0", "-o", str(output_file), "-f"]
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        assert proc.stdin is not None
        tar_stream: io.RawIOBase = proc.stdin  # type: ignore[assignment]
    else:
        proc = None
        tar_stream = gzip.GzipFile(
            filename="", mode="wb", compresslevel=min(max(level, 1), 9), fileobj=open(output_file, "wb")
        )

    try:
        with tarfile.open(fileobj=tar_stream, mode="w|") as tar:  # type: ignore[arg-type]
            for source in sources:
                source = Path(os.path.abspath(source))
                if not source.is_dir():
                    continue
                base_depth = len(source.parts)
                for root, dirs, files in os.walk(source):
                    rel_root = Path(root).relative_to(source)
                    # Apply excludes to directories (prune).
                    dirs[:] = [
                        d for d in dirs
                        if not _matches_exclude(
                            str((rel_root / d).as_posix()), excludes
                        )
                    ]
                    for name in sorted(dirs) + sorted(files):
                        full = Path(root) / name
                        rel = Path(root).relative_to(*source.parts[:base_depth])
                        arcname = str(full.relative_to(source))
                        if _matches_exclude(arcname, excludes):
                            continue
                        try:
                            tar.add(str(full), arcname=arcname, recursive=False)
                            if progress_callback:
                                progress_callback(arcname)
                        except (OSError, tarfile.TarError) as exc:
                            # Non-fatal: skip unreadable entries but record the issue.
                            if progress_callback:
                                progress_callback(f"SKIP {arcname}: {exc}")
                            continue
    finally:
        if proc is not None:
            try:
                proc.stdin.close()
            except OSError:
                pass
            stderr_out = proc.stderr.read() if proc.stderr else b""
            returncode = proc.wait()
            if returncode != 0:
                try:
                    output_file.unlink()
                except OSError:
                    pass
                raise CompressionError(
                    f"zstd compression failed with exit code {returncode}: "
                    f"{stderr_out.decode(errors='replace').strip()}"
                )
        else:
            tar_stream.close()  # type: ignore[union-attr]

    return output_file


def verify_archive(path: Path, compression: str) -> bool:
    """Verify archive integrity without extracting it."""
    try:
        if compression == "zstd":
            if not zstd_available():
                return False
            result = subprocess.run(
                ["zstd", "-t", str(path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            return result.returncode == 0
        with gzip.open(path, "rb") as handle:
            while handle.read(1024 * 1024):
                pass
        return True
    except (OSError, EOFError, subprocess.SubprocessError):
        return False
