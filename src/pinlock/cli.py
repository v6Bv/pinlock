"""The `pinlock` command."""
import argparse
import getpass
import os
import pwd
import shutil
import subprocess
import sys
import time

from . import __version__, config, keymap, pam, pinstore

GUI_HINT = "Buttons: A=1 B=2 X=3 Y=4 LB=5 RB=6 ↑=7 →=8 ↓=9 ←=0, Start=Enter, View=Backspace"


def self_path():
    return os.path.realpath(sys.argv[0])


def need_root(what):
    if os.geteuid() != 0:
        sys.exit(f"{what} needs root: sudo pinlock {' '.join(sys.argv[1:])}")


def target_user(name):
    """The user to act on: given name, else whoever ran sudo/pkexec, else us."""
    if name:
        user = name
    elif "PKEXEC_UID" in os.environ:
        user = pwd.getpwuid(int(os.environ["PKEXEC_UID"])).pw_name
    else:
        user = os.environ.get("SUDO_USER") or getpass.getuser()
    try:
        pwd.getpwnam(user)
    except KeyError:
        sys.exit(f"no such user: {user}")
    if name and "PKEXEC_UID" in os.environ and \
            pwd.getpwnam(user).pw_uid != int(os.environ["PKEXEC_UID"]):
        sys.exit("can only change your own PIN through the setup app")
    return user


def cmd_set(args):
    need_root("Setting a PIN")
    user = target_user(args.user)
    if args.stdin:
        pin = sys.stdin.readline().strip()
    else:
        pin = getpass.getpass(f"New PIN for {user} ({pinstore.MIN_LEN}-{pinstore.MAX_LEN} digits): ")
        if pinstore.valid_pin(pin) and getpass.getpass("Again: ") != pin:
            sys.exit("PINs didn't match")
    try:
        pinstore.write_pin(user, pin)
    except ValueError as exc:
        sys.exit(str(exc))
    print(f"PIN set for {user}.")
    if not args.stdin:
        print(GUI_HINT)


def cmd_remove(args):
    need_root("Removing a PIN")
    user = target_user(args.user)
    print(f"PIN removed for {user}." if pinstore.remove_pin(user) else f"{user} has no PIN.")


def service_active():
    return subprocess.run(["systemctl", "is-active", "--quiet", "pinlockd.service"]).returncode == 0


def cmd_status(args):
    user = target_user(args.user)
    print(f"pinlock {__version__}")
    print(f"  service pinlockd: {'running' if service_active() else 'not running'}")
    print(f"  PIN for {user}: {'set' if pinstore.has_pin(user) else 'not set'}")
    for svc, state in pam.status().items():
        print(f"  {pam.SERVICES[svc]} ({svc}): {state}")
    pads = keymap.open_gamepads()
    print(f"  controllers: {', '.join(d.name for d in pads) or 'none found'}")


def cmd_test(args):
    import select
    pads = keymap.open_gamepads()
    if not pads:
        sys.exit("No controller found. Is it connected? (Try sudo if it is.)")
    for d in pads:
        print(f"{d.path}: {d.name}")
    print("Press buttons, Ctrl+C to stop.")
    names = dict(keymap.DIGITS, START="Enter", VIEW="Backspace")
    while True:
        ready, _, _ = select.select(pads, [], [])
        for d in ready:
            for ev in d.read():
                btn = keymap.button_pressed(ev)
                if btn:
                    print(f"{btn:6} -> {names.get(btn, '(unused)')}", flush=True)


def cmd_check(args):
    """pam_exec entry point: typed text on stdin, user in PAM_USER."""
    if os.environ.get("PAM_TYPE", "auth") != "auth":
        sys.exit(1)
    pin = sys.stdin.buffer.read(pinstore.MAX_LEN + 2).rstrip(b"\0\n").decode("ascii", "replace")
    try:
        ok = pinstore.check_pin(os.environ.get("PAM_USER", ""), pin)
    except ValueError:
        ok = False
    sys.exit(0 if ok else 1)


def cmd_pam(args):
    if args.action == "status":
        for svc, state in pam.status().items():
            print(f"{svc:14} {state:10} {pam.SERVICES[svc]}")
        return
    need_root("Changing PAM files")
    changed = pam.enable(self_path()) if args.action == "enable" else pam.disable()
    verb = "Enabled" if args.action == "enable" else "Disabled"
    print(f"{verb} for: {', '.join(changed)}" if changed else "Nothing to change.")


def cmd_on_unlock(args):
    """Run the user's unlock action. Started by pinlockd inside the user's manager."""
    settings = config.load()
    if settings["action"] == "none":
        return
    # On a fresh login the desktop may still be starting: wait for it, then
    # pick up its display variables (this unit started before they existed).
    for _ in range(60):
        if subprocess.run(["systemctl", "--user", "-q", "is-active",
                           "graphical-session.target"]).returncode == 0:
            break
        time.sleep(1)
    time.sleep(2)
    env = dict(os.environ)
    out = subprocess.run(["systemctl", "--user", "show-environment"],
                         capture_output=True, text=True).stdout
    for line in out.splitlines():
        key, _, value = line.partition("=")
        if key in ("DISPLAY", "WAYLAND_DISPLAY", "XAUTHORITY", "XDG_CURRENT_DESKTOP",
                   "DBUS_SESSION_BUS_ADDRESS", "XDG_SESSION_TYPE"):
            env[key] = value
    if settings["action"] == "command":
        if settings["command"].strip():
            os.execvpe("/bin/sh", ["/bin/sh", "-c", settings["command"]], env)
        return
    if shutil.which("steam"):
        os.execvpe("steam", ["steam", "steam://open/bigpicture"], env)
    os.execvpe("flatpak", ["flatpak", "run", "com.valvesoftware.Steam",
                           "steam://open/bigpicture"], env)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="pinlock", description=(
        "Log in and unlock with a PIN typed on a game controller. "
        "Run pinlock-setup for the controller-friendly app."))
    ap.add_argument("--version", action="version", version=f"pinlock {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("set", help="set or change a PIN (root)")
    p.add_argument("user", nargs="?")
    p.add_argument("--stdin", action="store_true", help="read the PIN from stdin")
    p.set_defaults(func=cmd_set)
    p = sub.add_parser("remove", help="remove a PIN (root)")
    p.add_argument("user", nargs="?")
    p.set_defaults(func=cmd_remove)
    p = sub.add_parser("status", help="show what is set up")
    p.add_argument("user", nargs="?")
    p.set_defaults(func=cmd_status)
    sub.add_parser("test", help="show what each controller button types").set_defaults(func=cmd_test)
    p = sub.add_parser("pam", help="hook the login/lock screens into PAM (root)")
    p.add_argument("action", choices=["enable", "disable", "status"])
    p.set_defaults(func=cmd_pam)
    # Internal entry points, hidden from --help.
    sub.add_parser("check").set_defaults(func=cmd_check)
    sub.add_parser("on-unlock").set_defaults(func=cmd_on_unlock)

    args = ap.parse_args(argv)
    try:
        args.func(args)
    except KeyboardInterrupt:
        pass
