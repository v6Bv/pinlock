"""Turning the lock screen passkey panel on and off.

Plasma's lock screen (started by KWin) loads its QML from the shell package
named by PLASMA_DEFAULT_SHELL. pinlock ships a tiny shell package whose
LockScreen.qml is Plasma's own lock screen plus the passkey panel.

We set PLASMA_DEFAULT_SHELL for KWin's systemd user service only. plasmashell
reads the same variable, so it must never go into the whole session's
environment. As a safety net, plasmashell's own service also gets
UnsetEnvironment= for it, in case KWin ever shares its environment.
Everything here is per user and needs no root. KWin reads its
environment at startup, so changes apply from the next login.
"""
import os
import subprocess
import time

PACKAGE = "io.github.v6bv.pinlock"
KWIN_UNIT = "plasma-kwin_wayland.service"
SHELL_UNIT = "plasma-plasmashell.service"


def config_home():
    return os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")


def dropin_path(unit=KWIN_UNIT):
    return os.path.join(config_home(), "systemd", "user", f"{unit}.d", "pinlock.conf")


def package_installed():
    dirs = [os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")]
    dirs += (os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share").split(":")
    return any(os.path.exists(os.path.join(d, "plasma", "shells", PACKAGE, "metadata.json"))
               for d in dirs if d)


def enabled():
    return os.path.exists(dropin_path())


def _reload():
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)


def enable():
    if not package_installed():
        raise RuntimeError("pinlock's lock screen package isn't installed (run install.sh)")
    header = ("# Added by `pinlock lockscreen enable`: makes Plasma's lock screen show\n"
              "# the pinlock passkey panel. Remove with `pinlock lockscreen disable`.\n")
    for unit, line in ((SHELL_UNIT, "UnsetEnvironment=PLASMA_DEFAULT_SHELL"),
                       (KWIN_UNIT, f"Environment=PLASMA_DEFAULT_SHELL={PACKAGE}")):
        path = dropin_path(unit)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(f"{header}[Service]\n{line}\n")
    _reload()


def disable():
    changed = False
    for unit in (KWIN_UNIT, SHELL_UNIT):
        try:
            os.remove(dropin_path(unit))
            changed = True
        except FileNotFoundError:
            continue
        try:
            os.rmdir(os.path.dirname(dropin_path(unit)))
        except OSError:
            pass  # other drop-ins live there too
    if changed:
        _reload()


def status():
    """'on', 'on after next login' or 'off'."""
    out = subprocess.run(["systemctl", "--user", "show", KWIN_UNIT, "-p",
                          "ActiveEnterTimestampMonotonic"],
                         capture_output=True, text=True).stdout
    try:
        kwin_started_us = int(out.strip().partition("=")[2])
    except ValueError:
        kwin_started_us = 0
    if not enabled():
        return "off"
    if not kwin_started_us:
        return "on"
    # Compare the drop-in's age with when KWin started to tell if it's live yet.
    boot_s = float(open("/proc/uptime").read().split()[0])
    kwin_started = time.time() - boot_s + kwin_started_us / 1e6
    return "on" if os.path.getmtime(dropin_path()) < kwin_started else "on after next login"
