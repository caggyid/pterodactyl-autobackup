# Changelog

All notable changes to this project are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-09-02

### Added

- Initial production release.
- Backup engine: tar streaming with zstd (system binary) or gzip fallback.
- SHA-256 checksum generation and verification (`caggy-backup verify`).
- Google Drive integration via official Drive API v3 with OAuth 2.0,
  resumable chunked uploads, and retry with exponential backoff.
- Drive folder structure: `/CaggyID-Backups/<hostname>/<year>/<month>/`.
- SQLite backup history (`caggy-backup list`, `caggy-backup history`).
- Retention policy (keep_last / keep_daily / keep_weekly / keep_monthly)
  with `caggy-backup cleanup` and `--dry-run`.
- Restore with checksum verification, safety confirmation, and `--dry-run`
  (`caggy-backup restore <backup-id>`).
- Cron scheduler management (`caggy-backup cron install|remove|status`)
  with idempotent marked entries.
- Setup wizard (`caggy-backup setup`) and Google Drive connectivity test
  (`caggy-backup test-drive`).
- Installer (`scripts/install.sh`), uninstaller (`scripts/uninstall.sh`),
  and headless cron helper (`scripts/setup-cron.sh`).
- systemd service unit for timer-based operation.
- Automation-friendly CLI: `--non-interactive`, `--quiet`, `--verbose`,
  meaningful exit codes (0/1/2/3/4/5).
- Automated tests and GitHub Actions workflow for Python 3.10-3.13.
- Full documentation set in `docs/`.
