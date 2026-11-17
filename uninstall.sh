#!/bin/bash
# Remove pinlock and its login-screen hooks: sudo ./uninstall.sh
set -euo pipefail
cd "$(dirname "$0")"
[[ $EUID -eq 0 ]] || { echo "Run with sudo: sudo ./uninstall.sh"; exit 1; }
if [[ -x /usr/local/bin/pinlock ]]; then
    /usr/local/bin/pinlock pam disable
    # The lock screen panel is a per-user setting; undo it for whoever ran sudo.
    if [[ -n ${SUDO_USER:-} ]]; then
        sudo -u "$SUDO_USER" XDG_RUNTIME_DIR="/run/user/$(id -u "$SUDO_USER")" \
            /usr/local/bin/pinlock lockscreen disable >/dev/null 2>&1 || true
    fi
fi
systemctl disable --now pinlockd.service 2>/dev/null || true
make uninstall PREFIX=/usr/local
systemctl daemon-reload
echo "Removed. Saved PINs are still in /etc/pinlock (delete that folder to remove them)."
