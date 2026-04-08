#!/usr/bin/env bash
# install.sh – set up screen-ctrl on Raspberry Pi
# Run once as the user who will own the service (default: pi).
set -euo pipefail

INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="screen-ctrl"
APP_USER="${SUDO_USER:-pi}"

echo "=== screen-ctrl installer ==="
echo "Install dir : $INSTALL_DIR"
echo "Run as user : $APP_USER"
echo ""

# ── 1. System packages ────────────────────────────────────────────────────────
echo "[1/5] Installing system packages…"
apt-get update -qq
apt-get install -y --no-install-recommends \
    mosquitto \
    mosquitto-clients \
    mpv \
    libmpv2 \
    python3 \
    python3-pip \
    python3-venv \
    feh            # fallback image viewer (optional)

# ── 2. Python virtual environment ─────────────────────────────────────────────
echo "[2/5] Creating Python virtual environment…"
python3 -m venv "${INSTALL_DIR}/venv"
"${INSTALL_DIR}/venv/bin/pip" install --quiet --upgrade pip
"${INSTALL_DIR}/venv/bin/pip" install --quiet -r "${INSTALL_DIR}/requirements.txt"

# ── 3. Media directories ──────────────────────────────────────────────────────
echo "[3/5] Creating media directories…"
HOME_DIR=$(eval echo "~${APP_USER}")
mkdir -p "${HOME_DIR}/videos" "${HOME_DIR}/images" "${HOME_DIR}/audio"
chown -R "${APP_USER}:${APP_USER}" \
    "${HOME_DIR}/videos" \
    "${HOME_DIR}/images" \
    "${HOME_DIR}/audio"
echo "    Place your files in:"
echo "      ${HOME_DIR}/videos/  (video files)"
echo "      ${HOME_DIR}/images/  (background images)"
echo "      ${HOME_DIR}/audio/   (ambient + effects)"

# ── 4. Config file ────────────────────────────────────────────────────────────
echo "[4/5] Checking config…"
if [[ ! -f "${INSTALL_DIR}/config.yml" ]]; then
    echo "    Creating default config.yml – EDIT IT before starting the service."
    cp "${INSTALL_DIR}/config.yml.example" "${INSTALL_DIR}/config.yml" 2>/dev/null || true
else
    echo "    config.yml already exists – keeping it."
fi

# ── 5. Systemd service ────────────────────────────────────────────────────────
echo "[5/5] Installing systemd service…"
SERVICE_SRC="${INSTALL_DIR}/screen-ctrl.service"
SERVICE_DEST="/etc/systemd/system/${SERVICE_NAME}.service"

# Substitute actual paths into the service file
sed \
    -e "s|__INSTALL_DIR__|${INSTALL_DIR}|g" \
    -e "s|__APP_USER__|${APP_USER}|g" \
    "${SERVICE_SRC}" > "${SERVICE_DEST}"

systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"

echo ""
echo "=== Done! ==="
echo ""
echo "Next steps:"
echo "  1. Edit ${INSTALL_DIR}/config.yml  (set MQTT broker IP, filenames, volume)"
echo "  2. Copy your media files to ${HOME_DIR}/{videos,images,audio}/"
echo "  3. sudo systemctl start ${SERVICE_NAME}"
echo "  4. journalctl -fu ${SERVICE_NAME}   (to watch logs)"
