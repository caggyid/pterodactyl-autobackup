#!/usr/bin/env bash
# CaggyID Pterodactyl Backup - cron setup helper
# Prefer the CLI: caggy-backup cron install
# This script exists for headless installs without the interactive prompt.
set -euo pipefail

SCHEDULE="${1:-0 */6 * * *}"
MARKER_BEGIN="# CAGGY-BACKUP:BEGIN"
MARKER_END="# CAGGY-BACKUP:END"
BINARY="$(command -v caggy-backup || echo /usr/local/bin/caggy-backup)"

if [ ! -x "${BINARY}" ]; then
  echo "[ERROR] caggy-backup binary not found. Install the package first." >&2
  exit 1
fi

case "${SCHEDULE}" in
  every-6-hours)  SCHEDULE="0 */6 * * *" ;;
  every-12-hours) SCHEDULE="0 */12 * * *" ;;
  daily)          SCHEDULE="0 3 * * *" ;;
  weekly)         SCHEDULE="0 3 * * 0" ;;
esac

CURRENT="$(crontab -l 2>/dev/null || true)"
CLEANED="$(echo "${CURRENT}" | sed "/${MARKER_BEGIN}/,/${MARKER_END}/d")"
{
  echo "${CLEANED}" | sed -e '/^[[:space:]]*$/d'
  echo "${MARKER_BEGIN}"
  echo "${SCHEDULE} ${BINARY} backup --non-interactive >> /var/log/caggy-backup/cron.log 2>&1"
  echo "${MARKER_END}"
} | crontab -

echo "[OK] Cron installed: ${SCHEDULE} ${BINARY} backup --non-interactive"
crontab -l | tail -n 3
