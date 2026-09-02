"""Cron scheduler management.

Installs/removes a marked crontab entry using absolute paths and no
dependency on the interactive shell environment. All operations are
idempotent: repeated installs never create duplicate entries.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

MARKER_BEGIN = "# CAGGY-BACKUP:BEGIN"
MARKER_END = "# CAGGY-BACKUP:END"

SCHEDULE_PRESETS = {
    "every-6-hours": "0 */6 * * *",
    "every-12-hours": "0 */12 * * *",
    "daily": "0 3 * * *",
    "weekly": "0 3 * * 0",
}


class SchedulerError(Exception):
    pass


@dataclass
class CronStatus:
    installed: bool
    entry: str | None
    crontab: str


def get_crontab() -> str:
    """Read the current user crontab (empty when none exists)."""
    result = subprocess.run(
        ["crontab", "-l"], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        return ""
    return result.stdout


def set_crontab(content: str) -> None:
    result = subprocess.run(
        ["crontab", "-"], input=content, capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise SchedulerError(f"Failed to write crontab: {result.stderr.strip()}")


def build_entry(schedule: str, binary_path: str, extra_args: str = "") -> str:
    """Build the marked cron entry with absolute paths."""
    schedule = schedule.strip()
    if not schedule or len(schedule.split()) != 5:
        raise SchedulerError(
            f"Invalid cron expression: '{schedule}' (expected 5 fields, e.g. '0 */6 * * *')"
        )
    binary = Path(binary_path)
    if not binary.is_absolute():
        raise SchedulerError("Cron entry must use the absolute path of the caggy-backup binary")
    args = f" {extra_args.strip()}" if extra_args and extra_args.strip() else ""
    return (
        f"{MARKER_BEGIN}\n"
        f"{schedule} {binary}{args} >> /var/log/caggy-backup/cron.log 2>&1\n"
        f"{MARKER_END}"
    )


def install(schedule: str, binary_path: str, extra_args: str = "") -> None:
    """Install or replace the marked cron entry (idempotent)."""
    if not Path("/usr/bin/crontab").exists() and not Path("/usr/bin/crontab").is_file():
        # crontab may live elsewhere; detect via shutil.which
        import shutil as _shutil

        if not _shutil.which("crontab"):
            raise SchedulerError(
                "crontab not found. Install cron (e.g. 'apt install cron') and ensure the service is running."
            )

    entry = build_entry(schedule, binary_path, extra_args)
    current = get_crontab()

    # Remove any previously marked block, then append the fresh one.
    lines = current.splitlines()
    cleaned: list[str] = []
    inside = False
    for line in lines:
        if line.strip() == MARKER_BEGIN:
            inside = True
            continue
        if line.strip() == MARKER_END:
            inside = False
            continue
        if not inside:
            cleaned.append(line)

    new_content = "\n".join(cleaned).rstrip("\n")
    if new_content:
        new_content += "\n"
    new_content += entry + "\n"
    set_crontab(new_content)


def remove() -> bool:
    """Remove the marked cron entry. Returns True when something was removed."""
    current = get_crontab()
    if MARKER_BEGIN not in current:
        return False
    lines = current.splitlines()
    cleaned: list[str] = []
    inside = False
    for line in lines:
        if line.strip() == MARKER_BEGIN:
            inside = True
            continue
        if line.strip() == MARKER_END:
            inside = False
            continue
        if not inside:
            cleaned.append(line)
    new_content = "\n".join(cleaned).rstrip("\n")
    if new_content:
        set_crontab(new_content + "\n")
    else:
        set_crontab("")
    return True


def status() -> CronStatus:
    current = get_crontab()
    inside = False
    block_lines: list[str] = []
    for line in current.splitlines():
        if line.strip() == MARKER_BEGIN:
            inside = True
            continue
        if line.strip() == MARKER_END:
            inside = False
            continue
        if inside and line.strip():
            block_lines.append(line.strip())
    entry = " ".join(block_lines) if block_lines else None
    return CronStatus(installed=bool(block_lines), entry=entry, crontab=current)
