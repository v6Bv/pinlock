"""Storing and checking PINs.

Each user's PIN is a salted scrypt hash in /etc/pinlock/<user>, owned by root
and readable by the user's group: the KDE lock screen checks it as the user,
but changing it needs root.
"""
import hashlib
import hmac
import os
import pwd

PIN_DIR = os.environ.get("PINLOCK_DIR", "/etc/pinlock")
MIN_LEN, MAX_LEN = 4, 12
SCHEME = "scrypt1"
N, R, P = 2**14, 8, 1


def valid_pin(pin):
    return pin.isascii() and pin.isdigit() and MIN_LEN <= len(pin) <= MAX_LEN


def pin_path(user):
    if not user or "/" in user or user.startswith("."):
        raise ValueError(f"bad user name: {user!r}")
    return os.path.join(PIN_DIR, user)


def _hash(pin, salt):
    return hashlib.scrypt(pin.encode(), salt=salt, n=N, r=R, p=P, dklen=32)


def has_pin(user):
    return os.path.exists(pin_path(user))


def write_pin(user, pin):
    if not valid_pin(pin):
        raise ValueError(f"PIN must be {MIN_LEN}-{MAX_LEN} digits")
    gid = pwd.getpwnam(user).pw_gid
    salt = os.urandom(16)
    os.makedirs(PIN_DIR, mode=0o755, exist_ok=True)
    path = pin_path(user)
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(f"{SCHEME}${salt.hex()}${_hash(pin, salt).hex()}\n")
    os.chown(tmp, 0, gid)
    os.chmod(tmp, 0o640)
    os.replace(tmp, path)


def remove_pin(user):
    """Returns False if the user had no PIN."""
    try:
        os.remove(pin_path(user))
        return True
    except FileNotFoundError:
        return False


def check_pin(user, pin):
    # Anything that isn't a PIN (e.g. the real password) is rejected without
    # being hashed, and PAM carries on to the normal password check.
    if not valid_pin(pin):
        return False
    try:
        with open(pin_path(user)) as f:
            scheme, salt, stored = f.read().strip().split("$")
    except (OSError, ValueError):
        return False
    if scheme != SCHEME:
        return False
    return hmac.compare_digest(_hash(pin, bytes.fromhex(salt)).hex(), stored)
