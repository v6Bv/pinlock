"""Adding the PIN check to the login and lock screen PAM stacks.

For each supported service we put a marked block before its first auth line.
The block is `sufficient`, so a correct PIN logs in and anything else falls
through to the normal password check. sudo, su and SSH are never touched.

Enabling and disabling also clean up hooks that aren't in a marked block
(left by pre-release versions), so a service never ends up checked twice.
"""
import os
import re

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
# An unmarked hook: a pam_exec line running `pinlock check` (or the
# pre-release name, controller-pin), plus its comment and faillock line.
LEGACY_CHECK = re.compile(r"^\s*auth\s.*pam_exec\.so\s.*\b(pinlock|controller-pin) check\s*$")
LEGACY_COMMENT = re.compile(r"^# (pinlock|controller-pin): accept a controller PIN")
FAILLOCK_PREAUTH = re.compile(r"^\s*auth\s+required\s+pam_faillock\.so\s+preauth\s*$")


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
    """Remove marked blocks and any unmarked pinlock hooks."""
    lines, out, skipping = text.splitlines(keepends=True), [], False
    for i, line in enumerate(lines):
        if line.startswith(BEGIN):
            skipping = True
        elif skipping:
            skipping = not line.startswith(END)
        elif LEGACY_CHECK.match(line) or LEGACY_COMMENT.match(line):
            continue
        elif FAILLOCK_PREAUTH.match(line) and i + 1 < len(lines) and \
                LEGACY_CHECK.match(lines[i + 1]):
            continue  # the faillock line that belongs to an unmarked hook
        else:
            out.append(line)
    return "".join(out)


def _hooked(text):
    return text is not None and _strip(text) != text


def status():
    """{service: "enabled" | "available"} for services present on this system."""
    result = {}
    for svc in SERVICES:
        etc = _read(os.path.join(ETC, svc))
        if _hooked(etc):
            result[svc] = "enabled"
        elif etc is not None or os.path.exists(os.path.join(VENDOR, svc)):
            result[svc] = "available"
    return result


def enable(check_cmd):
    """Hook every service, leaving exactly one block in each. Returns the services changed."""
    changed = []
    for svc in status():
        dst = os.path.join(ETC, svc)
        current = _read(dst)
        lines = _strip(current or _read(os.path.join(VENDOR, svc))).splitlines(keepends=True)
        for i, line in enumerate(lines):
            if line.lstrip("-").startswith("auth"):
                lines.insert(i, block(check_cmd))
                break
        else:
            continue  # no auth section: nothing to hook
        if "".join(lines) != current:
            _write(dst, "".join(lines))
            changed.append(svc)
    return changed


def disable():
    """Remove every pinlock hook. Returns the services changed."""
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
