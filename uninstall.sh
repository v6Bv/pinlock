#!/bin/bash
# Remove pinlock and its login-screen hooks: sudo ./uninstall.sh
set -euo pipefail
cd "$(dirname "$0")"
[[ $EUID -eq 0 ]] || { echo "Run with sudo: sudo ./uninstall.sh"; exit 1; }
[[ -x /usr/local/bin/pinlock ]] && /usr/local/bin/pinlock pam disable
systemctl disable --now pinlockd.service 2>/dev/null || true
make uninstall PREFIX=/usr/local
systemctl daemon-reload
echo "Removed. Saved PINs are still in /etc/pinlock (delete that folder to remove them)."
