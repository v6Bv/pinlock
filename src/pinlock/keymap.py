"""Controller buttons, the digits they stand for, and gamepad detection.

Everything works in terms of button names ("A", "UP", "START", ...) so the
daemon, the setup app and the tester all agree on one mapping.
"""
from evdev import ecodes as e

# evdev key code -> button name. xpad reports the left face button as BTN_X
# and the top one as BTN_Y, matching the Xbox labels.
KEY_BUTTONS = {
    e.BTN_SOUTH: "A",
    e.BTN_EAST: "B",
    e.BTN_X: "X",
    e.BTN_Y: "Y",
    e.BTN_TL: "LB",
    e.BTN_TR: "RB",
    e.BTN_START: "START",
    e.BTN_SELECT: "VIEW",
    e.BTN_MODE: "GUIDE",
}
# D-pad arrives as hat axes: (axis, value) -> button name.
HAT_BUTTONS = {
    (e.ABS_HAT0Y, -1): "UP",
    (e.ABS_HAT0X, 1): "RIGHT",
    (e.ABS_HAT0Y, 1): "DOWN",
    (e.ABS_HAT0X, -1): "LEFT",
}
# Some pads (and Steam's virtual one) send the D-pad as buttons instead.
KEY_BUTTONS.update({
    e.BTN_DPAD_UP: "UP",
    e.BTN_DPAD_RIGHT: "RIGHT",
    e.BTN_DPAD_DOWN: "DOWN",
    e.BTN_DPAD_LEFT: "LEFT",
})

DIGITS = {
    "A": "1", "B": "2", "X": "3", "Y": "4", "LB": "5", "RB": "6",
    "UP": "7", "RIGHT": "8", "DOWN": "9", "LEFT": "0",
}
# Display order for legends: (button, label shown on screen).
LEGEND = [("A", "A"), ("B", "B"), ("X", "X"), ("Y", "Y"), ("LB", "LB"),
          ("RB", "RB"), ("UP", "↑"), ("RIGHT", "→"), ("DOWN", "↓"), ("LEFT", "←")]

# Name of the virtual keyboard pinlockd creates, so it never reads itself.
UINPUT_NAME = "pinlock virtual keyboard"


def button_pressed(ev):
    """Button name for a press event, or None (releases and sticks are ignored)."""
    if ev.type == e.EV_KEY and ev.value == 1:
        return KEY_BUTTONS.get(ev.code)
    if ev.type == e.EV_ABS:
        return HAT_BUTTONS.get((ev.code, ev.value))
    return None


def is_gamepad(dev):
    if dev.name == UINPUT_NAME:
        return False
    keys = dev.capabilities().get(e.EV_KEY, [])
    return e.BTN_SOUTH in keys and e.BTN_START in keys


def open_gamepads(skip_paths=(), not_pads=None):
    """Open every gamepad not already in skip_paths; returns InputDevices.

    not_pads, if given, is a dict that remembers devices already found not to
    be gamepads, so frequent rescans don't reopen every keyboard and mouse.
    A device node that was recreated (hotplug) is checked again.
    """
    import os
    import evdev
    pads = []
    for path in evdev.list_devices():
        if path in skip_paths:
            continue
        try:
            stamp = os.stat(path).st_ctime_ns
        except OSError:
            continue
        if not_pads is not None and not_pads.get(path) == stamp:
            continue
        try:
            dev = evdev.InputDevice(path)
        except OSError:
            continue
        if is_gamepad(dev):
            pads.append(dev)
        else:
            dev.close()
            if not_pads is not None:
                not_pads[path] = stamp
    return pads
