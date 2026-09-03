# CaggyID — Pterodactyl Node Auto Backup

[![Version](https://img.shields.io/badge/version-1.0.0-blue.svg)](pyproject.toml)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue.svg)](pyproject.toml)
[![License](https://img.shields.io/badge/license-CaggyID%20License-green.svg)](LICENSE)
[![Tests](https://github.com/caggyid/pterodactyl-autobackup/actions/workflows/tests.yml/badge.svg)](.github/workflows/tests.yml)

Automated Pterodactyl Node/Server backup system integrated with **Google Drive API v3**, **Cron scheduling**, **retention policy management**, **SHA-256 integrity verification**, **SQLite history logging**, and **non-destructive restore support**.

Developed by **CaggyID**

---

## Overview

**CaggyID Pterodactyl Node Backup** is a production-ready command line interface (CLI) tool designed for system administrators running Pterodactyl Wings / Node servers. It backs up server storage directly from the filesystem to Google Drive safely, efficiently, and non-invasively without disrupting running Wings services or Docker containers.

```text
╔══════════════════════════════════════════════╗
║       CaggyID Pterodactyl Backup             ║
║              v1.0.0                          ║
╚══════════════════════════════════════════════╝

[✓] Configuration loaded
[✓] Pterodactyl storage detected
[✓] Google Drive authenticated
[•] Creating backup...
[•] Compressing data (zstd level 3)...
[•] Uploading to Google Drive...
[✓] Backup completed successfully

Backup ID : 2026-09-02_203000
Size      : 2.41 GB
Duration  : 01m 42s
Location  : Google Drive / CaggyID-Backups
SHA256    : a8f4c92...
```

---

## Features

- 🚀 **High-Performance Streaming Compression**: Native `zstd` support with automatic streaming fallback to `gzip`.
- ☁️ **Official Google Drive API v3 Integration**: Uses OAuth 2.0 with secure token refresh. Never handles or stores Google account passwords.
- 🕒 **Idempotent Cron Scheduler**: Built-in cron management with marked blocks (`# CAGGY-BACKUP:BEGIN`) to prevent duplicate jobs.
- 🛡️ **Grandfather-Father-Son Retention**: Granular retention policy (`keep_last`, `keep_daily`, `keep_weekly`, `keep_monthly`).
- 🔒 **SHA-256 Integrity Verification**: Every backup includes SHA-256 checksums verified before upload and before restore.
- 🗄️ **SQLite History Tracker**: Tracks all backup jobs, file sizes, execution durations, Drive file IDs, and error states.
- 🔄 **Safe Restore Flow**: Dry-run verification mode, interactive prompt confirmations, and strict path-traversal prevention.
- ⚙️ **Automation-Friendly**: Non-interactive flags (`--non-interactive`, `--quiet`, `--yes`) and strict Linux exit codes (`0`-`5`).
- 📦 **Zero Wings Intrusion**: Reads storage from filesystem volumes without altering panel databases or Docker states.

---

## Architecture

```text
Local Storage (/var/lib/pterodactyl/volumes)
                    │
                    ▼
     [caggy-backup Streaming Engine]
                    │
         ┌──────────┴──────────┐
         ▼                     ▼
  zstd / gzip           SHA-256 Checksum
 compression            & metadata.json
         │                     │
         └──────────┬──────────┘
                    │
                    ▼
          [Google Drive API v3]
          (Resumable Chunked Upload)
                    │
                    ▼
      Google Drive / CaggyID-Backups / <hostname> / <year> / <month>
```

---

## Requirements

- **Operating System**: Ubuntu 22.04 LTS, Ubuntu 24.04 LTS, Debian 11, or Debian 12 (POSIX compliant).
- **Python**: Python 3.10+
- **System Binaries**: `zstd` (recommended for fast compression) and `cron` (for scheduling).
- **Google Cloud**: Active Google Cloud project with Google Drive API enabled and OAuth 2.0 Client credentials (`credentials.json`).

---

## Quick Start

### 1. One-Line Automatic Installation

```bash
curl -fsSL https://raw.githubusercontent.com/caggyid/pterodactyl-autobackup/main/scripts/install.sh | bash
```

### 2. Manual Installation

```bash
# Clone repository
git clone https://github.com/caggyid/pterodactyl-autobackup.git
cd caggyid-pterodactyl-backup

# Install package & dependencies
sudo python3 -m venv /opt/caggyid-pterodactyl-backup/.venv
sudo /opt/caggyid-pterodactyl-backup/.venv/bin/pip install .

# Symlink CLI binary
sudo ln -sf /opt/caggyid-pterodactyl-backup/.venv/bin/caggy-backup /usr/local/bin/caggy-backup

# Prepare runtime directories
sudo mkdir -p /etc/caggy-backup /var/log/caggy-backup
sudo chmod 700 /etc/caggy-backup
sudo cp config/config.example.yaml /etc/caggy-backup/config.yaml
```

---

## Setup & Configuration

### Interactive Setup Wizard

Run the interactive setup wizard to configure source directories, compression settings, Drive folder name, retention policy, and schedule:

```bash
caggy-backup setup
```

### Google Drive Authentication

1. Follow the step-by-step guide in [docs/google-drive.md](docs/google-drive.md) to download `credentials.json` from Google Cloud Console.
2. Place `credentials.json` in `/etc/caggy-backup/credentials.json` (`chmod 600`).
3. Authenticate and verify connection:
   ```bash
   caggy-backup test-drive
   ```

---

## CLI Command Reference

| Command | Description |
|---------|-------------|
| `caggy-backup setup` | Run interactive configuration wizard |
| `caggy-backup config` | Print current configuration in YAML format |
| `caggy-backup backup` | Run a backup job and upload to Google Drive |
| `caggy-backup backup --all` | Backup all server volumes |
| `caggy-backup backup --server <uuid>` | Backup specific server directory |
| `caggy-backup backup --no-upload` | Create compressed archive locally without uploading |
| `caggy-backup list` | List all historical backup records |
| `caggy-backup history` | Show detailed backup history |
| `caggy-backup status` | Check system status (sources, compression, Drive auth, cron) |
| `caggy-backup verify <backup-id>` | Verify SHA-256 checksum of local or remote backup |
| `caggy-backup restore <backup-id>` | Safely extract a backup archive |
| `caggy-backup restore <backup-id> --dry-run` | Test restore and check file count without extracting |
| `caggy-backup cleanup` | Run retention policy cleanup |
| `caggy-backup cleanup --dry-run` | Show backups scheduled for removal without deleting |
| `caggy-backup cron install` | Install cron schedule entry |
| `caggy-backup cron status` | Show installed cron entry |
| `caggy-backup cron remove` | Remove installed cron entry |
| `caggy-backup test-drive` | Test Google Drive connection and OAuth status |
| `caggy-backup version` | Display tool version and license info |
| `caggy-backup uninstall` | Uninstall cron and remove local configuration |

---

## Automation & Exit Codes

All CLI commands are optimized for automated Cron and CI/CD pipelines when invoked with `--non-interactive` or `--quiet`. Standard Linux exit codes returned:

- `0` : Success (`EXIT_OK`)
- `1` : General error (`EXIT_GENERAL`)
- `2` : Configuration error (`EXIT_CONFIG`)
- `3` : Authentication error (`EXIT_AUTH`)
- `4` : Backup or archive error (`EXIT_BACKUP`)
- `5` : Upload error (`EXIT_UPLOAD`)

Example cron job invocation:
```bash
0 */6 * * * /usr/local/bin/caggy-backup backup --all --non-interactive >> /var/log/caggy-backup/cron.log 2>&1
```

---

## Documentation

Comprehensive documentation is available in the [`docs/`](docs/) directory:

- [Installation Guide](docs/installation.md)
- [Google Drive OAuth Setup](docs/google-drive.md)
- [Configuration Reference](docs/configuration.md)
- [Cron & Scheduling](docs/cron.md)
- [Restore Procedures](docs/restore.md)
- [Troubleshooting & FAQs](docs/troubleshooting.md)

---

## Testing

Run unit tests locally with `pytest`:

```bash
pip install -e ".[dev]"
pytest --cov=caggy_backup --cov-report=term-missing
```

---

## Security

- Never commits or stores OAuth tokens or client secrets in source code.
- Enforces strict filesystem permissions (`0700` directories, `0600` files).
- Sanitizes log output to redact token/secret values.
- Validates source paths and extraction destinations against path-traversal exploits (`../../`).

Read our full [SECURITY.md](SECURITY.md) policy for vulnerability reporting procedures.

---

## License

This project is licensed under the **CaggyID License**. See the [LICENSE](LICENSE) file for complete details.

---

## Credits

Created and maintained by **CaggyID** ([caggyid.my.id](https://caggyid.my.id)).
 
