"""pinlockd: type a PIN from controller buttons on the login / lock screen.

Runs as root. While the active seat0 session is the login greeter or is locked,
controller presses become digit keystrokes on a virtual keyboard, so they land
in whatever password box has focus. Outside those screens it does nothing, so
games are unaffected.

If the screen unlocks right after the controller pressed Start, it runs
`pinlock on-unlock` in that user's session, which does whatever the user picked
in the setup app (Steam Big Picture by default).
"""
import os
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


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def loginctl(*args):
    return subprocess.run(["loginctl", *args], capture_output=True, text=True).stdout.strip()


class SessionWatcher(threading.Thread):
    """Polls logind: armed when seat0 shows the greeter or a locked session."""

    def __init__(self, on_unlock_cmd):
        super().__init__(daemon=True)
        self.on_unlock_cmd = on_unlock_cmd
        self.armed = False
        self.last_enter = -UNLOCK_WINDOW_SECONDS  # monotonic time of controller Start

    @staticmethod
    def active_session():
        return loginctl("show-seat", "seat0", "-p", "ActiveSession", "--value")

    def check(self):
        sid = self.active_session()
        if not sid:
            return True  # nobody active on the seat: the greeter is showing
        props = dict(line.split("=", 1) for line in loginctl(
            "show-session", sid, "-p", "Class", "-p", "LockedHint").splitlines()
            if "=" in line)
        return props.get("Class", "").startswith("greeter") or \
            props.get("LockedHint") == "yes"

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
    watcher = SessionWatcher(pinlock_cmd)
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
                if key == e.KEY_ENTER:
                    watcher.last_enter = time.monotonic()
