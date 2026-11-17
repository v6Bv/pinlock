"""Per-user settings in ~/.config/pinlock/pinlock.conf.

Only read in the user's own session (by `pinlock on-unlock` and the setup
app), never by root, so nothing here needs to be trusted.
"""
import configparser
import os

ACTIONS = {
    "steam": "Open Steam Big Picture",
    "none": "Do nothing",
    "command": "Run a custom command",
}
DEFAULTS = {"action": "steam", "command": ""}


def path():
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "pinlock", "pinlock.conf")


def load():
    cp = configparser.ConfigParser()
    cp.read(path())
    settings = dict(DEFAULTS)
    if cp.has_section("unlock"):
        settings.update({k: v for k, v in cp["unlock"].items() if k in DEFAULTS})
    if settings["action"] not in ACTIONS:
        settings["action"] = DEFAULTS["action"]
    return settings


def save(settings):
    cp = configparser.ConfigParser()
    cp["unlock"] = {k: settings.get(k, v) for k, v in DEFAULTS.items()}
    os.makedirs(os.path.dirname(path()), exist_ok=True)
    with open(path(), "w") as f:
        f.write("# What to do after unlocking with the controller.\n"
                "# action = steam | none | command\n")
        cp.write(f)
