import getpass
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from pinlock import keymap, lockscreen, pam, pinstore  # noqa: E402

USER = getpass.getuser()


class PinStoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        patches = [mock.patch.object(pinstore, "PIN_DIR", self.tmp.name),
                   mock.patch("os.chown")]  # tests don't run as root
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self.tmp.cleanup)

    def test_valid_pin(self):
        for pin in ("1234", "000000000000"):
            self.assertTrue(pinstore.valid_pin(pin), pin)
        for pin in ("123", "1234567890123", "12a4", "", "١٢٣٤", "hunter22"):
            self.assertFalse(pinstore.valid_pin(pin), pin)

    def test_round_trip(self):
        pinstore.write_pin(USER, "1357")
        self.assertTrue(pinstore.has_pin(USER))
        self.assertTrue(pinstore.check_pin(USER, "1357"))
        self.assertFalse(pinstore.check_pin(USER, "1358"))
        self.assertFalse(pinstore.check_pin(USER, "13570"))
        self.assertEqual(os.stat(pinstore.pin_path(USER)).st_mode & 0o777, 0o640)
        with open(pinstore.pin_path(USER)) as f:
            self.assertNotIn("1357", f.read())

    def test_remove(self):
        pinstore.write_pin(USER, "2468")
        self.assertTrue(pinstore.remove_pin(USER))
        self.assertFalse(pinstore.check_pin(USER, "2468"))
        self.assertFalse(pinstore.remove_pin(USER))

    def test_no_pin_or_bad_user(self):
        self.assertFalse(pinstore.check_pin(USER, "1234"))
        for bad in ("", "../etc/shadow", ".hidden"):
            with self.assertRaises(ValueError):
                pinstore.pin_path(bad)


class PamTest(unittest.TestCase):
    VENDOR_TEXT = "#%PAM-1.0\nauth include system-login\naccount include system-login\n"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.etc = os.path.join(self.tmp.name, "etc")
        self.vendor = os.path.join(self.tmp.name, "vendor")
        os.makedirs(self.etc)
        os.makedirs(self.vendor)
        for p in (mock.patch.object(pam, "ETC", self.etc),
                  mock.patch.object(pam, "VENDOR", self.vendor)):
            p.start()
            self.addCleanup(p.stop)

    def write(self, d, name, text):
        with open(os.path.join(d, name), "w") as f:
            f.write(text)

    def read(self, name):
        with open(os.path.join(self.etc, name)) as f:
            return f.read()

    def test_enable_disable_vendor_only(self):
        self.write(self.vendor, "plasmalogin", self.VENDOR_TEXT)
        self.assertEqual(pam.status(), {"plasmalogin": "available"})
        self.assertEqual(pam.enable("/usr/bin/pinlock"), ["plasmalogin"])
        text = self.read("plasmalogin")
        lines = text.splitlines()
        self.assertEqual(lines[0], "#%PAM-1.0")
        self.assertTrue(lines[1].startswith(pam.BEGIN))
        self.assertIn("sufficient  pam_exec.so      quiet expose_authtok /usr/bin/pinlock check", text)
        self.assertLess(text.index(pam.END), text.index("auth include system-login"))
        self.assertEqual(pam.enable("/usr/bin/pinlock"), [])  # idempotent
        self.assertEqual(pam.disable(), ["plasmalogin"])
        # /etc copy only existed because of us, so it's gone again.
        self.assertFalse(os.path.exists(os.path.join(self.etc, "plasmalogin")))

    def test_disable_keeps_local_edits(self):
        local = "#%PAM-1.0\n# my tweak\n-auth optional pam_foo.so\nauth include system-login\n"
        self.write(self.etc, "sddm", local)
        pam.enable("/usr/bin/pinlock")
        self.assertIn(pam.BEGIN, self.read("sddm"))
        self.assertLess(self.read("sddm").index(pam.BEGIN), self.read("sddm").index("-auth optional"))
        pam.disable()
        self.assertEqual(self.read("sddm"), local)

    def test_unknown_services_untouched(self):
        self.write(self.vendor, "sudo", self.VENDOR_TEXT)
        self.assertEqual(pam.status(), {})
        self.assertEqual(pam.enable("/usr/bin/pinlock"), [])


class CheckCommandTest(unittest.TestCase):
    """`pinlock check` as pam_exec runs it: typed text on stdin, NUL-terminated."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        with mock.patch.object(pinstore, "PIN_DIR", self.tmp.name), mock.patch("os.chown"):
            pinstore.write_pin(USER, "9070")

    def check(self, typed, user=USER, pam_type="auth"):
        env = dict(os.environ, PINLOCK_DIR=self.tmp.name, PAM_USER=user, PAM_TYPE=pam_type)
        return subprocess.run([sys.executable, os.path.join(ROOT, "bin", "pinlock"), "check"],
                              input=typed, env=env).returncode

    def test_check(self):
        self.assertEqual(self.check(b"9070\0"), 0)
        self.assertEqual(self.check(b"9070"), 0)
        self.assertEqual(self.check(b"9071\0"), 1)
        self.assertEqual(self.check(b"my real password\0"), 1)
        self.assertEqual(self.check(b""), 1)
        self.assertEqual(self.check(b"9070\0", user="nobody-here"), 1)
        self.assertEqual(self.check(b"9070\0", pam_type="password"), 1)


class LockscreenTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for p in (mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": self.tmp.name}),
                  mock.patch.object(lockscreen, "package_installed", return_value=True),
                  mock.patch.object(lockscreen.subprocess, "run")):
            p.start()
            self.addCleanup(p.stop)

    def read(self, unit):
        with open(lockscreen.dropin_path(unit)) as f:
            return f.read()

    def test_enable_sets_kwin_only(self):
        lockscreen.enable()
        self.assertTrue(lockscreen.enabled())
        self.assertIn("Environment=PLASMA_DEFAULT_SHELL=io.github.v6bv.pinlock",
                      self.read(lockscreen.KWIN_UNIT))
        # plasmashell must never pick up pinlock's shell package.
        self.assertIn("UnsetEnvironment=PLASMA_DEFAULT_SHELL", self.read(lockscreen.SHELL_UNIT))
        self.assertNotIn("Environment=PLASMA_DEFAULT_SHELL=", self.read(lockscreen.SHELL_UNIT)
                         .replace("UnsetEnvironment", ""))

    def test_disable_removes_both(self):
        lockscreen.enable()
        lockscreen.disable()
        self.assertFalse(lockscreen.enabled())
        for unit in (lockscreen.KWIN_UNIT, lockscreen.SHELL_UNIT):
            self.assertFalse(os.path.exists(os.path.dirname(lockscreen.dropin_path(unit))))
        lockscreen.disable()  # second time is a no-op

    def test_disable_keeps_other_dropins(self):
        lockscreen.enable()
        other = os.path.join(os.path.dirname(lockscreen.dropin_path()), "mine.conf")
        open(other, "w").close()
        lockscreen.disable()
        self.assertTrue(os.path.exists(other))

    def test_needs_package(self):
        with mock.patch.object(lockscreen, "package_installed", return_value=False):
            with self.assertRaises(RuntimeError):
                lockscreen.enable()
        self.assertFalse(lockscreen.enabled())


class OverlayDotsTest(unittest.TestCase):
    def test_dots_follow_typing(self):
        from evdev import ecodes as e
        from pinlock import daemon
        ov = daemon.Overlay("/bin/false")
        ov.proc = mock.Mock()
        sent = []
        ov.proc.stdin.write.side_effect = lambda b: sent.append(b.decode().strip())
        for key in (e.KEY_1, e.KEY_2, e.KEY_3, e.KEY_BACKSPACE, e.KEY_4, e.KEY_ENTER):
            ov.key(key)
        self.assertEqual(sent, ["show 1", "show 2", "show 3", "show 2", "show 3", "show 0"])
        ov.proc = None
        ov.key(e.KEY_1)  # no panel running: nothing to do, no crash


class KeymapTest(unittest.TestCase):
    def test_every_digit_once(self):
        self.assertEqual(sorted(keymap.DIGITS.values()), list("0123456789"))
        self.assertEqual([b for b, _ in keymap.LEGEND], list(keymap.DIGITS))


if __name__ == "__main__":
    unittest.main()
