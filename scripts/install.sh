#!/usr/bin/env bash
# CaggyID Pterodactyl Backup - installer
# Target: Ubuntu 20.04/22.04/24.04, Debian 11/12
# Usage: sudo bash scripts/install.sh
set -euo pipefail

APP_NAME="caggy-backup"
APP_DIR="/opt/caggyid-pterodactyl-backup"
CONFIG_DIR="/etc/caggy-backup"
LOG_DIR="/var/log/caggy-backup"
REPO_URL="${CAGGY_REPO_URL:-https://github.com/CaggyID/caggyid-pterodactyl-backup.git}"
REPO_BRANCH="${CAGGY_REPO_BRANCH:-main}"
PYTHON_MIN="3.10"

log()  { echo -e "[\033[1;32m✓\033[0m] $*"; }
warn() { echo -e "[!] $*"; }
die()  { echo -e "[ERROR] $*" >&2; exit 1; }

# Must run as root (or sudo)
if [ "$(id -u)" -ne 0 ]; then
  die "Please run as root: sudo bash scripts/install.sh"
fi

# 1. Check OS
if [ -f /etc/os-release ]; then
  . /etc/os-release
  log "Detected OS: ${PRETTY_NAME:-unknown}"
  case "${ID_LIKE:-} ${ID:-}" in
    *debian*) : ;;
    *) warn "Untested OS '${ID:-unknown}' - continuing anyway." ;;
  esac
else
  warn "Could not detect OS version."
fi

# 2. Check Python
if ! command -v python3 >/dev/null 2>&1; then
  log "Installing python3..."
  apt-get update -qq && apt-get install -y -qq python3 python3-venv python3-pip
fi
PY_VER="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
log "Python version: ${PY_VER}"
python3 -c "
import sys
major, minor = sys.version_info[:2]
if (major, minor) < (3, 10):
    print('[ERROR] Python >= ${PYTHON_MIN} required (found %d.%d)' % (major, minor)); sys.exit(1)
" || die "Python ${PYTHON_MIN}+ is required."

# 3. Install dependencies
export DEBIAN_FRONTEND=noninteractive
log "Installing system dependencies..."
apt-get update -qq
apt-get install -y -qq python3-venv python3-pip cron zstd git >/dev/null || {
  warn "Some system packages failed to install; install 'python3-venv cron zstd git' manually."
}
log "Enabling cron service..."
systemctl enable --now cron >/dev/null 2>&1 || service cron start >/dev/null 2>&1 || true

# 4. Create application directory
log "Creating application directory: ${APP_DIR}"
mkdir -p "${APP_DIR}"
if [ ! -d "${APP_DIR}/.git" ]; then
  log "Fetching source from ${REPO_URL} (${REPO_BRANCH})..."
  git clone --depth 1 --branch "${REPO_BRANCH}" "${REPO_URL}" "${APP_DIR}" 2>/dev/null \
    || warn "Clone failed; if you are installing from a local copy, copy this repository into ${APP_DIR}."
else
  log "Existing repository found; pulling latest changes..."
  git -C "${APP_DIR}" pull --ff-only 2>/dev/null || true
fi

# Local-copy fallback: if run from inside a repo checkout without network.
if [ ! -f "${APP_DIR}/pyproject.toml" ] && [ -f "./pyproject.toml" ]; then
  log "Using local source copy from $(pwd)"
  cp -r . "${APP_DIR}/"
fi

# 5. Create config directory
log "Creating config directory: ${CONFIG_DIR}"
mkdir -p "${CONFIG_DIR}"
chmod 700 "${CONFIG_DIR}"
if [ ! -f "${CONFIG_DIR}/config.yaml" ] && [ -f "${APP_DIR}/config/config.example.yaml" ]; then
  cp "${APP_DIR}/config/config.example.yaml" "${CONFIG_DIR}/config.yaml"
  log "Example configuration copied to ${CONFIG_DIR}/config.yaml (edit before first run)."
fi
touch "${CONFIG_DIR}/credentials.json.example" 2>/dev/null || true

# 6. Create log directory
log "Creating log directory: ${LOG_DIR}"
mkdir -p "${LOG_DIR}"
chmod 755 "${LOG_DIR}"

# 7. Install CLI into a virtualenv and expose the entry point
log "Installing Python package (virtualenv: ${APP_DIR}/.venv)..."
python3 -m venv "${APP_DIR}/.venv"
"${APP_DIR}/.venv/bin/pip" install --upgrade pip >/dev/null
"${APP_DIR}/.venv/bin/pip" install "${APP_DIR}" >/dev/null
cat > /usr/local/bin/${APP_NAME} <<EOF
#!/usr/bin/env bash
exec "${APP_DIR}/.venv/bin/caggy-backup" "\$@"
EOF
chmod 755 /usr/local/bin/${APP_NAME}

# 8. Permissions
chmod 600 "${CONFIG_DIR}"/config.yaml 2>/dev/null || true
chmod 755 /usr/local/bin/${APP_NAME}

# 9. Verify installation
if /usr/local/bin/${APP_NAME} version >/dev/null 2>&1; then
  log "Installation verified."
  /usr/local/bin/${APP_NAME} version
else
  die "Installation verification failed - run '${APP_NAME} version' to debug."
fi

# 10. Next steps
cat <<NEXT

============================================================
 CaggyID Pterodactyl Backup installed successfully!
============================================================

Next steps:

  1. Place your Google OAuth credentials.json:
       cp credentials.json ${CONFIG_DIR}/credentials.json

  2. Review configuration:
       sudo nano ${CONFIG_DIR}/config.yaml

  3. Run the setup wizard:
       caggy-backup setup

  4. Test Google Drive:
       caggy-backup test-drive

  5. First backup:
       caggy-backup backup

  6. Enable automatic backups:
       caggy-backup cron install

Documentation: https://github.com/CaggyID/caggyid-pterodactyl-backup/tree/main/docs
NEXT
