#!/usr/bin/env bash
# CaggyID Pterodactyl Backup - uninstaller
# Usage: sudo bash scripts/uninstall.sh
set -euo pipefail

APP_NAME="caggy-backup"
APP_DIR="/opt/caggyid-pterodactyl-backup"
CONFIG_DIR="/etc/caggy-backup"
LOG_DIR="/var/log/caggy-backup"

confirm() {
  read -r -p "$1 [y/N] " answer
  [ "${answer:-n}" = "y" ] || [ "${answer:-n}" = "Y" ]
}

echo "CaggyID Pterodactyl Backup - uninstaller"
echo

# Remove cron entry first (via the CLI when available).
if command -v "${APP_NAME}" >/dev/null 2>&1; then
  if confirm "Remove the cron schedule entry?"; then
    "${APP_NAME}" cron remove 2>/dev/null || true
    echo "[OK] Cron entry removed (if present)."
  fi
else
  echo "[•] ${APP_NAME} not found on PATH; skipping cron removal."
fi

if confirm "Remove application directory ${APP_DIR}?"; then
  rm -rf "${APP_DIR}"
  echo "[OK] Removed ${APP_DIR}"
fi

if [ -f /usr/local/bin/${APP_NAME} ]; then
  rm -f /usr/local/bin/${APP_NAME}
  echo "[OK] Removed /usr/local/bin/${APP_NAME}"
fi

if confirm "Remove configuration directory ${CONFIG_DIR} (contains credentials)?"; then
  rm -rf "${CONFIG_DIR}"
  echo "[OK] Removed ${CONFIG_DIR}"
fi

if confirm "Remove log directory ${LOG_DIR}?"; then
  rm -rf "${LOG_DIR}"
  echo "[OK] Removed ${LOG_DIR}"
fi

echo
echo "Uninstall complete. Your Google Drive data was NOT deleted."
