"""Configuration loading, validation, and environment overrides."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List

import yaml

from .utils import (
    EXIT_CONFIG,
    ensure_dir,
    validate_source_path,
)

DEFAULT_CONFIG_PATHS = [
    "/etc/caggy-backup/config.yaml",
    "~/.caggy-backup/config.yaml",
    "./config.yaml",
]


class ConfigError(Exception):
    """Raised when configuration is missing or invalid."""

    exit_code = EXIT_CONFIG

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


@dataclass
class CompressionConfig:
    type: str = "zstd"  # zstd | gzip
    level: int = 3

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "CompressionConfig":
        data = data or {}
        ctype = str(data.get("type", "zstd")).lower()
        if ctype not in ("zstd", "gzip"):
            raise ConfigError(
                f"backup.compression.type must be 'zstd' or 'gzip', got '{ctype}'"
            )
        level = int(data.get("level", 3))
        if not 1 <= level <= 19:
            raise ConfigError("backup.compression.level must be between 1 and 19")
        return cls(type=ctype, level=level)


@dataclass
class GoogleDriveConfig:
    folder_name: str = "CaggyID-Backups"
    credentials_file: str = "/etc/caggy-backup/credentials.json"
    token_file: str = "/etc/caggy-backup/token.json"

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "GoogleDriveConfig":
        data = data or {}
        return cls(
            folder_name=str(data.get("folder_name", "CaggyID-Backups")).strip() or "CaggyID-Backups",
            credentials_file=str(data.get("credentials_file", "/etc/caggy-backup/credentials.json")),
            token_file=str(data.get("token_file", "/etc/caggy-backup/token.json")),
        )


@dataclass
class RetentionConfig:
    enabled: bool = True
    keep_last: int = 7
    keep_daily: int = 7
    keep_weekly: int = 4
    keep_monthly: int = 6

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "RetentionConfig":
        data = data or {}
        return cls(
            enabled=bool(data.get("enabled", True)),
            keep_last=int(data.get("keep_last", 7)),
            keep_daily=int(data.get("keep_daily", 7)),
            keep_weekly=int(data.get("keep_weekly", 4)),
            keep_monthly=int(data.get("keep_monthly", 6)),
        )


@dataclass
class ScheduleConfig:
    enabled: bool = False
    cron: str = "0 */6 * * *"

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ScheduleConfig":
        data = data or {}
        return cls(
            enabled=bool(data.get("enabled", False)),
            cron=str(data.get("cron", "0 */6 * * *")),
        )


@dataclass
class LoggingConfig:
    level: str = "INFO"
    directory: str = "/var/log/caggy-backup"

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "LoggingConfig":
        data = data or {}
        level = str(data.get("level", "INFO")).upper()
        if level not in ("INFO", "WARNING", "ERROR", "DEBUG"):
            raise ConfigError(
                f"logging.level must be INFO, WARNING, ERROR, or DEBUG (got '{level}')"
            )
        return cls(level=level, directory=str(data.get("directory", "/var/log/caggy-backup")))


@dataclass
class Config:
    sources: List[Path] = field(default_factory=list)
    exclude: List[str] = field(default_factory=list)
    temp_directory: Path = Path("/tmp/caggy-backup")
    stop_servers: bool = False
    compression: CompressionConfig = field(default_factory=CompressionConfig)
    google_drive: GoogleDriveConfig = field(default_factory=GoogleDriveConfig)
    retention: RetentionConfig = field(default_factory=RetentionConfig)
    schedule: ScheduleConfig = field(default_factory=ScheduleConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    path: Path | None = None

    # ------------------------------------------------------------------
    @classmethod
    def load(cls, config_path: str | Path | None = None) -> "Config":
        """Load configuration from YAML plus environment overrides.

        Priority: CLI flag > CAGGY_CONFIG env > defaults list.
        Environment variables (CAGGY_*) always override YAML values.
        """
        path = cls._resolve_path(config_path)
        data: dict[str, Any] = {}
        if path is not None and Path(path).exists():
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    loaded = yaml.safe_load(handle)
                if loaded is not None:
                    if not isinstance(loaded, dict):
                        raise ConfigError(f"Invalid configuration format in {path}: top level must be a mapping")
                    data = loaded
            except yaml.YAMLError as exc:
                raise ConfigError(f"Failed to parse configuration file {path}: {exc}") from exc
            cls.path = Path(path)  # type: ignore[misc]
        elif config_path is not None:
            # Explicit path requested but missing -> hard error.
            raise ConfigError(f"Configuration file not found: {config_path}")

        backup = data.get("backup") or {}
        if not isinstance(backup, dict):
            raise ConfigError("'backup' section must be a mapping")

        sources_raw = backup.get("source") or []
        if isinstance(sources_raw, str):
            sources_raw = [sources_raw]
        if not isinstance(sources_raw, list):
            raise ConfigError("backup.source must be a list of directories")
        exclude_raw = backup.get("exclude") or []
        if isinstance(exclude_raw, str):
            exclude_raw = [exclude_raw]

        cfg = cls(
            sources=[Path(os.path.abspath(os.path.expanduser(str(s)))) for s in sources_raw],
            exclude=[str(e) for e in exclude_raw],
            temp_directory=Path(
                os.path.expanduser(str(backup.get("temp_directory", "/tmp/caggy-backup")))
            ),
            stop_servers=bool(backup.get("stop_servers", False)),
            compression=CompressionConfig.from_dict(backup.get("compression")),
            google_drive=GoogleDriveConfig.from_dict(data.get("google_drive")),
            retention=RetentionConfig.from_dict(data.get("retention")),
            schedule=ScheduleConfig.from_dict(data.get("schedule")),
            logging=LoggingConfig.from_dict(data.get("logging")),
        )
        if cls.path is not None:
            cfg.path = Path(path) if path is not None else None
        cfg._apply_env_overrides()

        if not cfg.sources:
            raise ConfigError(
                "No backup source configured. Set 'backup.source' in config.yaml "
                "or run 'caggy-backup setup'."
            )
        for source in cfg.sources:
            try:
                validate_source_path(str(source))
            except ValueError as exc:
                raise ConfigError(str(exc)) from exc
        return cfg

    @staticmethod
    def _resolve_path(config_path: str | Path | None) -> Path | None:
        if config_path is not None:
            path = Path(os.path.expanduser(str(config_path)))
        else:
            env = os.environ.get("CAGGY_CONFIG")
            if env:
                path = Path(os.path.expanduser(env))
            else:
                for candidate in DEFAULT_CONFIG_PATHS:
                    if Path(os.path.expanduser(candidate)).exists():
                        return Path(candidate)
                return None
        return path

    def _apply_env_overrides(self) -> None:
        sources_env = os.environ.get("CAGGY_BACKUP_SOURCES")
        if sources_env:
            self.sources = [
                Path(os.path.abspath(os.path.expanduser(s.strip())))
                for s in sources_env.split(",")
                if s.strip()
            ]
        credentials_env = os.environ.get("CAGGY_CREDENTIALS_FILE")
        if credentials_env:
            self.google_drive.credentials_file = credentials_env
        token_env = os.environ.get("CAGGY_TOKEN_FILE")
        if token_env:
            self.google_drive.token_file = token_env
        folder_env = os.environ.get("CAGGY_GDRIVE_FOLDER")
        if folder_env:
            self.google_drive.folder_name = folder_env.strip()
        log_dir_env = os.environ.get("CAGGY_LOG_DIRECTORY")
        if log_dir_env:
            self.logging.directory = log_dir_env
        log_level_env = os.environ.get("CAGGY_LOG_LEVEL")
        if log_level_env:
            level = log_level_env.upper()
            if level in ("INFO", "WARNING", "ERROR", "DEBUG"):
                self.logging.level = level

    def validate_gdrive_files(self) -> None:
        cred = Path(os.path.expanduser(self.google_drive.credentials_file))
        if not cred.exists():
            raise ConfigError(
                f"Google Drive credentials file not found: {cred}\n"
                "Run 'caggy-backup setup' or download credentials.json from Google Cloud."
            )

    def ensure_runtime_dirs(self) -> None:
        ensure_dir(self.temp_directory)

    def to_dict(self) -> dict[str, Any]:
        return {
            "backup": {
                "source": [str(s) for s in self.sources],
                "exclude": list(self.exclude),
                "temp_directory": str(self.temp_directory),
                "stop_servers": self.stop_servers,
                "compression": {"type": self.compression.type, "level": self.compression.level},
            },
            "google_drive": {
                "folder_name": self.google_drive.folder_name,
                "credentials_file": self.google_drive.credentials_file,
                "token_file": self.google_drive.token_file,
            },
            "retention": {
                "enabled": self.retention.enabled,
                "keep_last": self.retention.keep_last,
                "keep_daily": self.retention.keep_daily,
                "keep_weekly": self.retention.keep_weekly,
                "keep_monthly": self.retention.keep_monthly,
            },
            "schedule": {"enabled": self.schedule.enabled, "cron": self.schedule.cron},
            "logging": {"level": self.logging.level, "directory": self.logging.directory},
        }

    def save_yaml(self, path: Path) -> None:
        ensure_dir(path.parent)
        with open(path, "w", encoding="utf-8") as handle:
            yaml.safe_dump(self.to_dict(), handle, sort_keys=False, default_flow_style=False)
        if os.name == "posix":
            os.chmod(path, 0o600)
