"""Adding the PIN check to the login and lock screen PAM stacks.

For each supported service we put a marked block before its first auth line.
The block is `sufficient`, so a correct PIN logs in and anything else falls
through to the normal password check. sudo, su and SSH are never touched.
"""
import os

# Login screens and lock screens pinlock knows how to hook.
SERVICES = {
    "plasmalogin": "Plasma Login Manager",
    "sddm": "SDDM",
    "lightdm": "LightDM",
    "gdm-password": "GDM / GNOME lock screen",
    "kde": "KDE lock screen",
}
ETC = os.environ.get("PINLOCK_PAM_ETC", "/etc/pam.d")
VENDOR = os.environ.get("PINLOCK_PAM_VENDOR", "/usr/lib/pam.d")
BEGIN = "# BEGIN pinlock (managed by `pinlock pam`; accepts a controller PIN, else falls through)"
END = "# END pinlock"


def block(check_cmd):
    return "\n".join([
        BEGIN,
        "auth       required    pam_faillock.so  preauth",
        f"auth       sufficient  pam_exec.so      quiet expose_authtok {check_cmd} check",
        END,
    ]) + "\n"


def _read(path):
    try:
        with open(path) as f:
            return f.read()
    except FileNotFoundError:
        return None


def _write(path, text):
    tmp = path + ".pinlock-tmp"
    with open(tmp, "w") as f:
        f.write(text)
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)


def _strip(text):
    out, skipping = [], False
    for line in text.splitlines(keepends=True):
        if line.startswith(BEGIN):
            skipping = True
        elif skipping and line.startswith(END):
            skipping = False
        elif not skipping:
            out.append(line)
    return "".join(out)


def status():
    """{service: "enabled" | "available"} for services present on this system."""
    result = {}
    for svc in SERVICES:
        etc = _read(os.path.join(ETC, svc))
        if etc is not None and BEGIN in etc:
            result[svc] = "enabled"
        elif etc is not None or os.path.exists(os.path.join(VENDOR, svc)):
            result[svc] = "available"
    return result


def enable(check_cmd):
    """Hook every available service. Returns the services changed."""
    changed = []
    for svc, state in status().items():
        if state != "available":
            continue
        dst = os.path.join(ETC, svc)
        text = _read(dst) or _read(os.path.join(VENDOR, svc))
        lines = text.splitlines(keepends=True)
        for i, line in enumerate(lines):
            if line.lstrip("-").startswith("auth"):
                lines.insert(i, block(check_cmd))
                break
        else:
            continue  # no auth section: nothing to hook
        _write(dst, "".join(lines))
        changed.append(svc)
    return changed


def disable():
    """Remove the block everywhere. Returns the services changed."""
    changed = []
    for svc, state in status().items():
        if state != "enabled":
            continue
        dst = os.path.join(ETC, svc)
        text = _strip(_read(dst))
        # If /etc only existed because we copied the vendor file, drop it again.
        if text == _read(os.path.join(VENDOR, svc)):
            os.remove(dst)
        else:
            _write(dst, text)
        changed.append(svc)
    return changed
