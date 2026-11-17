"""pinlockd: type a PIN from controller buttons on the login / lock screen.

Runs as root. While the active seat0 session is the login greeter or is locked,
controller presses become digit keystrokes on a virtual keyboard, so they land
in whatever password box has focus. Outside those screens it does nothing, so
games are unaffected.

On the login screen it also shows the passkey panel (`pinlock overlay`, run as
the greeter's user on the greeter's display). The lock screen gets the same
panel from pinlock's lock screen package instead, since KWin hides other
windows while the screen is locked.

If the screen unlocks right after the controller pressed Start, it runs
`pinlock on-unlock` in that user's session, which does whatever the user picked
in the setup app (Steam Big Picture by default).
"""
import os
import pwd
import select
import subprocess
import sys
import threading
import time

import evdev
from evdev import ecodes as e

from . import keymap

BUTTON_KEYS = {btn: getattr(e, f"KEY_{digit}") for btn, digit in keymap.DIGITS.items()}
BUTTON_KEYS.update({"START": e.KEY_ENTER, "VIEW": e.KEY_BACKSPACE})
RESCAN_SECONDS = 2.0
STATE_SECONDS = 1.0
UNLOCK_WINDOW_SECONDS = 15.0


class Overlay:
    """The login screen passkey panel, driven over its stdin."""

    def __init__(self, pinlock_cmd):
        self.cmd = pinlock_cmd
        self.proc = None
        self.user = None
        self.dots = 0
        self.retry_at = 0.0
        self.lock = threading.Lock()

    def ensure(self, user):
        with self.lock:
            if self.proc and self.proc.poll() is None and self.user == user:
                return
            if self.proc and self.proc.poll() is not None:
                log(f"login screen panel exited ({self.proc.returncode}); retrying in 30s")
                self.retry_at = time.monotonic() + 30
            self._stop()
            if time.monotonic() < self.retry_at:
                return
            try:
                pw = pwd.getpwnam(user)
            except KeyError:
                return
            runtime = f"/run/user/{pw.pw_uid}"
            try:
                sockets = sorted(f for f in os.listdir(runtime)
                                 if f.startswith("wayland-") and not f.endswith(".lock"))
            except OSError:
                sockets = []
            if not sockets:
                return  # greeter isn't on Wayland (yet); try again next poll
            env = {
                "PATH": "/usr/local/bin:/usr/bin:/bin",
                "HOME": pw.pw_dir or "/",
                "XDG_RUNTIME_DIR": runtime,
                "WAYLAND_DISPLAY": sockets[0],
                "QT_QPA_PLATFORM": "wayland",
                "QT_WAYLAND_SHELL_INTEGRATION": "layer-shell",
                "LANG": os.environ.get("LANG", "C.UTF-8"),
            }
            try:
                self.proc = subprocess.Popen([self.cmd, "overlay"], stdin=subprocess.PIPE, env=env,
                                             cwd="/", user=pw.pw_uid, group=pw.pw_gid,
                                             extra_groups=[])
            except OSError as exc:
                log(f"couldn't start the login screen panel: {exc}")
                return
            self.user = user
            self.dots = 0
            log(f"login screen panel started for greeter user {user} on {sockets[0]}")

    def _stop(self):
        if self.proc:
            try:
                self.proc.stdin.close()
                self.proc.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                self.proc.kill()
            self.proc = None
            self.user = None

    def stop(self):
        with self.lock:
            self._stop()

    def key(self, key):
        """Mirror what was typed into the password box, and show the panel."""
        with self.lock:
            if not self.proc:
                return
            if key == e.KEY_BACKSPACE:
                self.dots = max(0, self.dots - 1)
            elif key == e.KEY_ENTER:
                self.dots = 0
            else:
                self.dots = min(32, self.dots + 1)
            try:
                self.proc.stdin.write(f"show {self.dots}\n".encode())
                self.proc.stdin.flush()
            except OSError:
                self.proc = None


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def loginctl(*args):
    return subprocess.run(["loginctl", *args], capture_output=True, text=True).stdout.strip()


class SessionWatcher(threading.Thread):
    """Polls logind: armed when seat0 shows the greeter or a locked session."""

    def __init__(self, on_unlock_cmd, overlay):
        super().__init__(daemon=True)
        self.on_unlock_cmd = on_unlock_cmd
        self.overlay = overlay
        self.armed = False
        self.greeter_user = None
        self.last_enter = -UNLOCK_WINDOW_SECONDS  # monotonic time of controller Start

    @staticmethod
    def active_session():
        return loginctl("show-seat", "seat0", "-p", "ActiveSession", "--value")

    def check(self):
        self.greeter_user = None
        sid = self.active_session()
        if not sid:
            return True  # nobody active on the seat: the greeter is showing
        props = dict(line.split("=", 1) for line in loginctl(
            "show-session", sid, "-p", "Class", "-p", "LockedHint", "-p", "Name").splitlines()
            if "=" in line)
        if props.get("Class", "").startswith("greeter"):
            self.greeter_user = props.get("Name") or None
            return True
        return props.get("LockedHint") == "yes"

    def run(self):
        while True:
            try:
                armed = self.check()
            except Exception as exc:  # never let a logind hiccup kill the thread
                log(f"session check failed: {exc}")
                armed = False
            if armed != self.armed:
                log("armed (login/lock screen)" if armed else "disarmed")
                if not armed and time.monotonic() - self.last_enter < UNLOCK_WINDOW_SECONDS:
                    self.on_unlock()
            self.armed = armed
            if armed and self.greeter_user:
                self.overlay.ensure(self.greeter_user)
            else:
                self.overlay.stop()
            time.sleep(STATE_SECONDS)

    def on_unlock(self):
        user = loginctl("show-session", self.active_session(), "-p", "Name", "--value")
        if not user or user == "root":
            return
        log(f"controller unlock by {user}: running on-unlock action")
        subprocess.Popen(["systemd-run", "--user", f"--machine={user}@.host",
                          "--collect", "--quiet", "--", self.on_unlock_cmd, "on-unlock"])


def run(pinlock_cmd):
    if os.geteuid() != 0:
        sys.exit("pinlockd must run as root")
    keyboard = evdev.UInput({e.EV_KEY: sorted(set(BUTTON_KEYS.values()))},
                            name=keymap.UINPUT_NAME)
    overlay = Overlay(pinlock_cmd)
    watcher = SessionWatcher(pinlock_cmd, overlay)
    watcher.start()
    pads = {}  # fd -> InputDevice
    last_scan = 0.0

    def tap(key):
        keyboard.write(e.EV_KEY, key, 1)
        keyboard.syn()
        keyboard.write(e.EV_KEY, key, 0)
        keyboard.syn()

    while True:
        if time.monotonic() - last_scan > RESCAN_SECONDS:
            last_scan = time.monotonic()
            for dev in keymap.open_gamepads({d.path for d in pads.values()}):
                pads[dev.fd] = dev
                log(f"watching {dev.path}: {dev.name}")

        ready, _, _ = select.select(list(pads), [], [], RESCAN_SECONDS)
        for fd in ready:
            dev = pads[fd]
            try:
                events = list(dev.read())
            except OSError:  # unplugged
                log(f"lost {dev.path}")
                del pads[fd]
                continue
            if not watcher.armed:
                continue
            for ev in events:
                key = BUTTON_KEYS.get(keymap.button_pressed(ev))
                if key is None:
                    continue
                tap(key)
                overlay.key(key)
                if key == e.KEY_ENTER:
                    watcher.last_enter = time.monotonic()
