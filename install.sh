#!/bin/bash
# Install pinlock from this folder: sudo ./install.sh
set -euo pipefail
cd "$(dirname "$0")"
[[ $EUID -eq 0 ]] || { echo "Run with sudo: sudo ./install.sh"; exit 1; }

missing=()
python3 -c 'import evdev' 2>/dev/null || missing+=("python-evdev")
python3 -c 'import PyQt6' 2>/dev/null || missing+=("python-pyqt6 (setup app and login screen panel)")
[[ -d /usr/lib/qt6/qml/org/kde/layershell ]] || missing+=("layer-shell-qt (login screen panel)")
command -v pkexec >/dev/null || missing+=("polkit")
if ((${#missing[@]})); then
    echo "Missing: ${missing[*]}"
    echo "On Arch: pacman -S python-evdev python-pyqt6 layer-shell-qt polkit"
    python3 -c 'import evdev' 2>/dev/null || exit 1
fi

make install PREFIX=/usr/local
/usr/local/bin/pinlock pam enable
systemctl daemon-reload
systemctl enable pinlockd.service
systemctl restart pinlockd.service   # pick up new code when upgrading
echo
echo "Installed. Open \"pinlock\" from your app menu (or run pinlock-setup) to set your PIN"
echo "and turn on the lock screen panel."
