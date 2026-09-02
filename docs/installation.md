# Installation

## Requirements

- Ubuntu 22.04 / 24.04 or Debian 11 / 12 (other systemd-based distros usually work)
- Python 3.10 or newer
- `zstd` (recommended) - installed automatically by the installer
- A Google Cloud project with the Drive API enabled (see `google-drive.md`)

## One-line install

```bash
curl -fsSL https://raw.githubusercontent.com/CaggyID/caggyid-pterodactyl-backup/main/scripts/install.sh | bash
```

> Reviewing the script before piping it to bash is good practice:
> `curl -fsSL <url> -o install.sh && less install.sh && sudo bash install.sh`

## Manual install

```bash
git clone https://github.com/CaggyID/caggyid-pterodactyl-backup.git
cd caggyid-pterodactyl-backup

sudo python3 -m venv /opt/caggyid-pterodactyl-backup/.venv
sudo /opt/caggyid-pterodactyl-backup/.venv/bin/pip install .

sudo ln -sf /opt/caggyid-pterodactyl-backup/.venv/bin/caggy-backup /usr/local/bin/caggy-backup

sudo mkdir -p /etc/caggy-backup /var/log/caggy-backup
sudo chmod 700 /etc/caggy-backup
sudo cp config/config.example.yaml /etc/caggy-backup/config.yaml
```

## What the installer does

1. Checks the OS and Python version.
2. Installs system dependencies (`python3-venv`, `cron`, `zstd`, `git`).
3. Creates `/opt/caggyid-pterodactyl-backup` (application).
4. Creates `/etc/caggy-backup` (configuration, 0700).
5. Creates `/var/log/caggy-backup` (logs).
6. Installs the `caggy-backup` CLI into `/usr/local/bin`.
7. Verifies the installation and prints next steps.

## Verify

```bash
caggy-backup version
```

```text
CaggyID Pterodactyl Backup
Version: 1.0.0
License: CaggyID License
```

## Uninstall

```bash
sudo bash scripts/uninstall.sh
```

or use the CLI shortcut: `caggy-backup uninstall`. Both ask for
confirmation before removing configuration or data.
