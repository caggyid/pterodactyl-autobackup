"""CaggyID Pterodactyl Backup command line interface.

Built with Typer. All commands are automation-friendly: they never depend
on an interactive prompt unless explicitly required (setup, restore
confirmation), respect --quiet/--verbose, and return meaningful exit
codes:

    0 = success
    1 = general error
    2 = configuration error
    3 = authentication error
    4 = backup error
    5 = upload error
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List, Optional

import typer

from . import __license__, __project__, __version__
from .backup import BackupError, discover_servers, run_backup
from .compression import resolve_compression_type
from .config import CompressionConfig, Config, ConfigError, RetentionConfig, ScheduleConfig
from .database import BackupDatabase, default_db_path, parse_backup_created_at
from .gdrive import GoogleDriveError, GoogleDriveAuthError
from .logger import setup_logging
from .retention import run_cleanup
from .restore import RestoreError, run_restore
from .scheduler import SchedulerError, SCHEDULE_PRESETS, install as cron_install, remove as cron_remove, status as cron_status
from .utils import (
    EXIT_AUTH,
    EXIT_BACKUP,
    EXIT_CONFIG,
    EXIT_GENERAL,
    EXIT_OK,
    EXIT_UPLOAD,
    get_hostname,
    human_size,
    validate_source_path,
)

app = typer.Typer(
    name="caggy-backup",
    help="CaggyID Pterodactyl Node Auto Backup - backup Pterodactyl node data to Google Drive.",
    no_args_is_help=True,
    add_completion=False,
    pretty_exceptions_enable=False,
)

VERBOSE = False
QUIET = False


def _log(message: str, marker: str = "•") -> None:
    if not QUIET:
        typer.echo(f"[{marker}] {message}")


def _ok(message: str) -> None:
    _log(message, marker="✓")


def _warn(message: str) -> None:
    typer.echo(f"[!] {message}")


def _error(message: str, hint: str | None = None) -> None:
    typer.echo(f"[ERROR] {message}", err=True)
    if hint:
        typer.echo(hint, err=True)


def _banner() -> None:
    if QUIET:
        return
    width = 48
    typer.echo("╔" + "═" * width + "╗")
    typer.echo(f"║{'CaggyID Pterodactyl Backup':^{width}}║")
    typer.echo(f"║{f'v{__version__}':^{width}}║")
    typer.echo("╚" + "═" * width + "╝")


def _load_config(config_flag: Optional[Path]) -> Config:
    try:
        cfg = Config.load(config_flag)
        _ok("Configuration loaded")
        return cfg
    except ConfigError as exc:
        _error(str(exc), hint="Run: caggy-backup setup")
        raise typer.Exit(code=EXIT_CONFIG)


def _get_db() -> BackupDatabase:
    return BackupDatabase()


@app.callback()
def main(
    verbose: bool = typer.Option(False, "--verbose", help="Enable verbose (debug) output."),
    quiet: bool = typer.Option(False, "--quiet", help="Suppress non-essential output (for cron/automation)."),
    config: Optional[Path] = typer.Option(None, "--config", "-c", help="Path to config.yaml."),
    version: bool = typer.Option(False, "--version", help="Show version and exit."),
) -> None:
    """CaggyID Pterodactyl Node Auto Backup."""
    global VERBOSE, QUIET
    VERBOSE = verbose
    QUIET = quiet
    if version:
        typer.echo(f"{__project__}")
        typer.echo(f"Version: {__version__}")
        typer.echo(f"License: {__license__}")
        raise typer.Exit(code=EXIT_OK)
    try:
        cfg = Config.load(config) if (config or os.environ.get("CAGGY_CONFIG") or _default_config_exists()) else None
    except ConfigError:
        cfg = None
    level = "DEBUG" if verbose else "INFO"
    if cfg is not None:
        setup_logging(cfg.logging.level, cfg.logging.directory, verbose=verbose)
    else:
        setup_logging(level, None, verbose=verbose)


def _default_config_exists() -> bool:
    from .config import DEFAULT_CONFIG_PATHS

    return any(Path(os.path.expanduser(p)).exists() for p in DEFAULT_CONFIG_PATHS)


# ----------------------------------------------------------------------
# setup
# ----------------------------------------------------------------------
@app.command()
def setup() -> None:
    """Interactive setup wizard (sources, Drive folder, compression, retention, schedule)."""
    _banner()
    typer.echo("CaggyID Backup Setup")
    typer.echo("")

    # [1/6] Source directory
    default_source = "/var/lib/pterodactyl/volumes"
    while True:
        source = typer.prompt(
            f"[1/6] Backup source directory", default=default_source, show_default=True
        )
        try:
            validate_source_path(source)
            break
        except ValueError as exc:
            _warn(str(exc))
    sources = [source]

    extra = typer.prompt("      Add another source? (comma separated, empty to skip)", default="")
    for item in extra.split(","):
        if item.strip():
            try:
                validate_source_path(item)
                sources.append(item.strip())
            except ValueError as exc:
                _warn(f"Skipped: {exc}")

    # [2/6] Drive folder
    drive_folder = typer.prompt("[2/6] Google Drive folder", default="CaggyID-Backups", show_default=True)

    # [3/6] Compression
    comp_type = typer.prompt("[3/6] Compression (zstd/gzip)", default="zstd", show_default=True).lower()
    if comp_type not in ("zstd", "gzip"):
        _warn("Unknown type, using gzip")
        comp_type = "gzip"

    # [4/6] Retention
    keep_last = int(typer.prompt("[4/6] Retention: keep last N backups", default=7, show_default=True))

    # [5/6] Schedule
    typer.echo("[5/6] Schedule:")
    typer.echo("  1) Every 6 hours  2) Every 12 hours  3) Daily  4) Weekly  5) Custom cron")
    choice = typer.prompt("  Choose", default="1", show_default=True)
    schedule_map = {"1": SCHEDULE_PRESETS["every-6-hours"], "2": SCHEDULE_PRESETS["every-12-hours"], "3": SCHEDULE_PRESETS["daily"], "4": SCHEDULE_PRESETS["weekly"]}
    cron_expr = schedule_map.get(choice, "")
    if choice == "5" or not cron_expr:
        cron_expr = typer.prompt("  Custom cron expression", default="0 */6 * * *", show_default=True)

    # [6/6] Test Drive connection
    cfg = Config(
        sources=[Path(os.path.abspath(os.path.expanduser(s))) for s in sources],
        compression=CompressionConfig(type=comp_type),
    )
    cfg.google_drive.folder_name = drive_folder.strip() or "CaggyID-Backups"
    cfg.retention = RetentionConfig(enabled=True, keep_last=keep_last)
    cfg.schedule = ScheduleConfig(enabled=True, cron=cron_expr)

    typer.echo("[6/6] Testing Google Drive connection...")
    drive_ok = False
    try:
        from . import gdrive as _gdrive

        creds = _gdrive.authenticate(Path(cfg.google_drive.credentials_file), Path(cfg.google_drive.token_file))
        service = _gdrive.build_service(creds)
        user = _gdrive.test_connection(service)
        _ok(f"Google Drive connected as {user.get('emailAddress', user.get('displayName', 'unknown'))}")
        drive_ok = True
    except (GoogleDriveAuthError, GoogleDriveError) as exc:
        _warn(f"Google Drive not ready: {exc}")
        typer.echo("        Follow docs/google-drive.md to create credentials.json, then run: caggy-backup test-drive")

    # Save config
    config_path = Path(os.environ.get("CAGGY_CONFIG", "/etc/caggy-backup/config.yaml"))
    if os.name == "nt" or not _writable(config_path.parent if config_path.parent.exists() else config_path.parent):
        config_path = Path.home() / ".caggy-backup" / "config.yaml"
    try:
        cfg.save_yaml(config_path)
        _ok(f"Configuration saved: {config_path}")
    except OSError as exc:
        _error(f"Could not save configuration: {exc}")
        raise typer.Exit(code=EXIT_CONFIG)

    typer.echo("")
    typer.echo("Next steps:")
    if not drive_ok:
        typer.echo("  1. Complete Google Drive setup: caggy-backup test-drive")
        typer.echo("  2. First backup: caggy-backup backup")
        typer.echo("  3. Schedule backups: caggy-backup cron install")
    else:
        typer.echo("  1. First backup: caggy-backup backup")
        typer.echo("  2. Schedule backups: caggy-backup cron install")


def _writable(directory: Path) -> bool:
    try:
        directory.mkdir(parents=True, exist_ok=True)
        probe = directory / ".caggy-write-probe"
        probe.touch()
        probe.unlink()
        return True
    except OSError:
        return False


# ----------------------------------------------------------------------
# config
# ----------------------------------------------------------------------
@app.command("config")
def config_cmd(
    config: Optional[Path] = typer.Option(None, "--config", "-c", help="Path to config.yaml."),
) -> None:
    """Show the current configuration."""
    cfg = _load_config(config)
    import yaml as _yaml

    typer.echo(_yaml.safe_dump(cfg.to_dict(), sort_keys=False))


# ----------------------------------------------------------------------
# backup
# ----------------------------------------------------------------------
@app.command()
def backup(
    server: Optional[List[str]] = typer.Option(None, "--server", "-s", help="Backup specific server(s) by name (repeatable)."),
    all_servers: bool = typer.Option(False, "--all", help="Backup all servers under the sources."),
    non_interactive: bool = typer.Option(False, "--non-interactive", help="Never prompt; safe for automation."),
    no_upload: bool = typer.Option(False, "--no-upload", help="Create the archive but skip Google Drive upload."),
    config: Optional[Path] = typer.Option(None, "--config", "-c", help="Path to config.yaml."),
) -> None:
    """Create a backup and upload it to Google Drive."""
    cfg = _load_config(config)
    cfg.ensure_runtime_dirs()
    hostname = get_hostname()
    servers = discover_servers(cfg.sources)

    _ok("Pterodactyl storage detected" if servers else "No server volumes detected; using full source dirs")

    selected = list(server) if (server and not all_servers) else None

    try:
        result = run_backup(
            cfg,
            selected_servers=selected,
            upload=not no_upload,
            progress=lambda m: _log(m),
        )
        if not QUIET:
            typer.echo("")
            typer.echo(f"Backup ID : {result.backup_id}")
            typer.echo(f"Size      : {human_size(result.archive_size)}")
            mins, secs = divmod(int(result.duration_sec), 60)
            typer.echo(f"Duration  : {mins:02d}m {secs:02d}s")
            location = "Google Drive / " + cfg.google_drive.folder_name if result.uploaded else "local only (not uploaded)"
            typer.echo(f"Location  : {location}")
            typer.echo(f"SHA256    : {result.checksum}")
        _ok("Backup completed successfully" if not no_upload else "Backup created (upload skipped)")
    except BackupError as exc:
        code = exc.exit_code
        _error(str(exc), hint="Run 'caggy-backup setup' to review configuration" if code in (EXIT_CONFIG, EXIT_AUTH) else None)
        raise typer.Exit(code=code)
    except KeyboardInterrupt:
        _error("Backup interrupted by user")
        raise typer.Exit(code=EXIT_GENERAL)


# ----------------------------------------------------------------------
# list / history / status / verify
# ----------------------------------------------------------------------
@app.command("list")
def list_cmd(
    limit: int = typer.Option(20, "--limit", "-l", help="Maximum entries to show."),
    config: Optional[Path] = typer.Option(None, "--config", "-c", help="Path to config.yaml."),
) -> None:
    """List backups recorded in the history database."""
    db = _get_db()
    records = db.list_all(limit=limit)
    if not records:
        typer.echo("No backups found. Run: caggy-backup backup")
        return
    typer.echo(f"{'BACKUP ID':<22} {'SIZE':>10}   {'STATUS':<10} {'DATE'}")
    typer.echo("-" * 68)
    for record in records:
        dt = parse_backup_created_at(record)
        typer.echo(
            f"{record.id:<22} {human_size(record.size):>10}   {record.status:<10} {dt.strftime('%d %b %Y %H:%M')}"
        )


@app.command("history")
def history_cmd(
    limit: int = typer.Option(50, "--limit", "-l", help="Maximum entries to show."),
) -> None:
    """Show detailed backup history."""
    list_cmd(limit=limit, config=None)


@app.command()
def status(
    config: Optional[Path] = typer.Option(None, "--config", "-c", help="Path to config.yaml."),
) -> None:
    """Show backup system status (config, storage, Drive, cron, history)."""
    _banner()
    try:
        cfg = Config.load(config)
        _ok("Configuration loaded")
    except ConfigError as exc:
        _error(str(exc))
        raise typer.Exit(code=EXIT_CONFIG)

    for source in cfg.sources:
        exists = source.is_dir()
        _log(f"Source: {source} - {'OK' if exists else 'MISSING'}", marker="✓" if exists else "!")

    from .compression import zstd_available

    ctype = resolve_compression_type(cfg.compression.type)
    if ctype != cfg.compression.type:
        _warn(f"zstd not installed; falling back to gzip (install 'zstd' for better performance)")
    else:
        _log(f"Compression: {ctype} level {cfg.compression.level}", marker="✓")
    _ = zstd_available

    from .database import default_db_path as _ddp

    db = BackupDatabase(_ddp())
    total = len(db.list_all())
    typer.echo(f"[•] History: {total} backup(s) recorded in {db.db_path}")

    try:
        from . import gdrive as _gdrive

        creds = _gdrive.authenticate(Path(cfg.google_drive.credentials_file), Path(cfg.google_drive.token_file))
        service = _gdrive.build_service(creds)
        user = _gdrive.test_connection(service)
        _ok(f"Google Drive authenticated ({user.get('emailAddress', 'unknown')})")
    except (GoogleDriveAuthError, GoogleDriveError, Exception) as exc:
        _warn(f"Google Drive not authenticated: {type(exc).__name__}")

    try:
        st = cron_status()
        if st.installed:
            _ok(f"Cron installed: {st.entry}")
        else:
            _log("Cron: not installed", marker="•")
    except SchedulerError:
        _log("Cron: unavailable on this system", marker="•")


@app.command()
def verify(
    backup_id: str = typer.Argument(..., help="Backup ID to verify."),
    config: Optional[Path] = typer.Option(None, "--config", "-c", help="Path to config.yaml."),
) -> None:
    """Verify a backup's checksum (local archive or Drive copy)."""
    cfg = _load_config(config)
    db = _get_db()
    record = db.get(backup_id)
    if record is None:
        _error(f"Backup '{backup_id}' not found in history")
        raise typer.Exit(code=EXIT_GENERAL)

    from .restore import resolve_backup_artifacts, verify_archive_checksum

    try:
        archive_path, checksum_path, _comp = resolve_backup_artifacts(cfg, db, record)
        ok, actual = verify_archive_checksum(archive_path, checksum_path)
    except (RestoreError, GoogleDriveAuthError, GoogleDriveError) as exc:
        _error(f"Verification failed: {exc}")
        raise typer.Exit(code=EXIT_UPLOAD)

    if ok:
        _ok(f"Backup {backup_id} verified (SHA256: {actual})")
        raise typer.Exit(code=EXIT_OK)
    _error(
        f"Checksum mismatch for {backup_id}.\nComputed: {actual}\n"
        + (f"Expected: {checksum_path.read_text(encoding='utf-8').strip()}" if checksum_path else "No stored checksum found.")
    )
    raise typer.Exit(code=EXIT_BACKUP)


# ----------------------------------------------------------------------
# restore
# ----------------------------------------------------------------------
@app.command()
def restore(
    backup_id: str = typer.Argument(..., help="Backup ID to restore (see: caggy-backup list)."),
    target: Optional[Path] = typer.Option(None, "--target", "-t", help="Restore target directory (default: original source)."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Verify only; do not extract."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt (automation)."),
    config: Optional[Path] = typer.Option(None, "--config", "-c", help="Path to config.yaml."),
) -> None:
    """Restore a backup with safety confirmation."""
    cfg = _load_config(config)
    db = _get_db()
    record = db.get(backup_id)
    if record is None:
        _error(f"Backup '{backup_id}' not found in history. Use: caggy-backup list")
        raise typer.Exit(code=EXIT_GENERAL)

    target_dir = target or (Path(cfg.sources[0]) if cfg.sources else Path.cwd())
    if not dry_run and not yes:
        typer.echo("")
        typer.echo("WARNING:")
        typer.echo("Restoring this backup may overwrite existing server data.")
        typer.echo("")
        typer.echo(f"Backup:\n{backup_id}")
        typer.echo("")
        if not typer.confirm("Continue?"):
            typer.echo("Restore cancelled.")
            raise typer.Exit(code=EXIT_OK)

    try:
        result = run_restore(cfg, db, record, target_dir, dry_run=dry_run, progress=lambda m: _log(m))
        if result.get("dry_run"):
            typer.echo(f"[DRY-RUN] {result['entries']} entries would be extracted into {result['target']}")
        _ok("Restore completed" if not dry_run else "Dry-run completed")
    except (RestoreError, GoogleDriveAuthError, GoogleDriveError) as exc:
        _error(str(exc))
        raise typer.Exit(code=EXIT_BACKUP)


# ----------------------------------------------------------------------
# cleanup
# ----------------------------------------------------------------------
@app.command()
def cleanup(
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be deleted without deleting."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation (automation)."),
    keep_drive: bool = typer.Option(False, "--keep-drive", help="Only remove local artifacts, keep Drive copies."),
    config: Optional[Path] = typer.Option(None, "--config", "-c", help="Path to config.yaml."),
) -> None:
    """Apply the retention policy and remove old backups."""
    cfg = _load_config(config)
    db = _get_db()

    plan = run_cleanup(cfg, db, dry_run=True)
    if not plan.delete:
        _ok("Nothing to clean - all backups are within the retention policy")
        raise typer.Exit(code=EXIT_OK)

    typer.echo(f"Retention policy would remove {len(plan.delete)} backup(s):")
    for record in plan.delete:
        typer.echo(f"  - {record.id} ({human_size(record.size)})")

    if dry_run:
        typer.echo("[DRY-RUN] Nothing was deleted.")
        raise typer.Exit(code=EXIT_OK)

    if not yes:
        if not typer.confirm("Delete these backups now?"):
            typer.echo("Cleanup cancelled.")
            raise typer.Exit(code=EXIT_OK)

    run_cleanup(cfg, db, dry_run=False, delete_drive=not keep_drive, progress=lambda m: _log(m))
    _ok(f"Cleanup complete ({len(plan.delete)} backup(s) removed)")


# ----------------------------------------------------------------------
# cron
# ----------------------------------------------------------------------
cron_app = typer.Typer(help="Install/remove/show the cron schedule.", no_args_is_help=True)
app.add_typer(cron_app, name="cron")


@cron_app.command("install")
def cron_install_cmd(
    schedule: Optional[str] = typer.Option(None, "--schedule", "-s", help="Preset (every-6-hours|every-12-hours|daily|weekly) or raw cron expression."),
    custom: bool = typer.Option(False, "--custom", help="Prompt for a custom cron expression."),
) -> None:
    """Install the cron schedule (idempotent - no duplicate entries)."""
    expression = _resolve_schedule(schedule, custom)
    binary = _find_binary()
    try:
        cron_install(expression, str(binary))
        _ok(f"Cron installed: {expression} {binary} backup")
    except SchedulerError as exc:
        _error(str(exc))
        raise typer.Exit(code=EXIT_GENERAL)


@cron_app.command("remove")
def cron_remove_cmd() -> None:
    """Remove the cron schedule."""
    try:
        removed = cron_remove()
    except SchedulerError as exc:
        _error(str(exc))
        raise typer.Exit(code=EXIT_GENERAL)
    _ok("Cron entry removed" if removed else "No cron entry found")


@cron_app.command("status")
def cron_status_cmd() -> None:
    """Show the installed cron entry."""
    try:
        st = cron_status()
    except SchedulerError as exc:
        _error(str(exc))
        raise typer.Exit(code=EXIT_GENERAL)
    if st.installed:
        typer.echo("[✓] Cron installed:")
        typer.echo(f"    {st.entry}")
    else:
        typer.echo("[•] No caggy-backup cron entry installed.")


def _resolve_schedule(schedule: Optional[str], custom: bool) -> str:
    if custom:
        return typer.prompt("Cron expression", default="0 */6 * * *")
    if schedule:
        return SCHEDULE_PRESETS.get(schedule, schedule)
    typer.echo("Choose a schedule:")
    typer.echo("  1) Every 6 hours  2) Every 12 hours  3) Daily  4) Weekly  5) Custom")
    choice = typer.prompt("Choose", default="1")
    mapping = {"1": SCHEDULE_PRESETS["every-6-hours"], "2": SCHEDULE_PRESETS["every-12-hours"], "3": SCHEDULE_PRESETS["daily"], "4": SCHEDULE_PRESETS["weekly"]}
    if choice in mapping:
        return mapping[choice]
    return typer.prompt("Custom cron expression")


def _find_binary() -> str:
    for candidate in ("/usr/local/bin/caggy-backup", "/usr/bin/caggy-backup"):
        if Path(candidate).exists():
            return candidate
    # Fall back to the interpreter-based invocation.
    import shutil as _shutil

    found = _shutil.which("caggy-backup")
    if found:
        return found
    raise SchedulerError("caggy-backup binary not found on PATH; install the package first.")


# ----------------------------------------------------------------------
# test-drive
# ----------------------------------------------------------------------
@app.command("test-drive")
def test_drive_cmd(
    config: Optional[Path] = typer.Option(None, "--config", "-c", help="Path to config.yaml."),
) -> None:
    """Test Google Drive authentication and folder access."""
    cfg = _load_config(config)
    _log("Authenticating with Google Drive...")
    try:
        from . import gdrive as _gdrive

        creds = _gdrive.authenticate(Path(cfg.google_drive.credentials_file), Path(cfg.google_drive.token_file))
        service = _gdrive.build_service(creds)
        user = _gdrive.test_connection(service)
        folder_id = _gdrive.get_folder_path(service, [cfg.google_drive.folder_name])
        _ok(f"Connected as: {user.get('emailAddress', user.get('displayName', 'unknown'))}")
        _ok(f"Folder ready: /{cfg.google_drive.folder_name} (id: {folder_id})")
    except GoogleDriveAuthError as exc:
        _error(str(exc))
        raise typer.Exit(code=EXIT_AUTH)
    except GoogleDriveError as exc:
        _error(str(exc))
        raise typer.Exit(code=EXIT_UPLOAD)


# ----------------------------------------------------------------------
# uninstall
# ----------------------------------------------------------------------
@app.command()
def uninstall() -> None:
    """Uninstall cron and optionally remove local configuration/data."""
    if not typer.confirm("This will remove the cron entry and can delete local config/data. Continue?"):
        typer.echo("Uninstall cancelled.")
        raise typer.Exit(code=EXIT_OK)

    try:
        if cron_remove():
            _ok("Cron entry removed")
        else:
            _log("No cron entry found")
    except SchedulerError as exc:
        _warn(str(exc))

    if typer.confirm("Remove local history database and config?", default=False):
        db_path = default_db_path()
        if db_path.exists():
            db_path.unlink()
            _ok(f"Removed {db_path}")
        for cfg_path in (Path.home() / ".caggy-backup" / "config.yaml",):
            if cfg_path.exists():
                cfg_path.unlink()
                _ok(f"Removed {cfg_path}")

    typer.echo("Package files remain installed; remove them with scripts/uninstall.sh if desired.")


# ----------------------------------------------------------------------
# version
# ----------------------------------------------------------------------
@app.command()
def version() -> None:
    """Show version information."""
    typer.echo(f"{__project__}")
    typer.echo(f"Version: {__version__}")
    typer.echo(f"License: {__license__}")


def run() -> None:
    """Console entry point."""
    try:
        app()
    except typer.Exit:
        raise
    except KeyboardInterrupt:
        sys.stderr.write("[ERROR] Interrupted\n")
        sys.exit(EXIT_GENERAL)


if __name__ == "__main__":
    run()
