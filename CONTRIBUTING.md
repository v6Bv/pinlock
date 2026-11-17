# Contributing

Thanks for helping. Bug reports, "works on my setup" reports, and pull
requests are all welcome.

## Easiest ways to help

- **Try it on your login screen.** SDDM, GDM, LightDM and GNOME's lock
  screen are untested. Open a
  [login screen report](https://github.com/v6Bv/pinlock/issues/new?template=login_screen_report.yml)
  whether it worked or not.
- **Try your controller.** Run `pinlock test` and check that every button
  shows the right digit. If one is wrong, open a bug report with the
  controller's name.

## Development setup

```bash
git clone https://github.com/v6Bv/pinlock
cd pinlock
make test                # unit tests, no root needed
./bin/pinlock-setup      # setup app, straight from the checkout
./bin/pinlock status
```

Saving a PIN from the checkout calls `pkexec ./bin/pinlock`, which works
without installing.

To try changes to the service or the PAM hookup for real:

```bash
sudo ./install.sh                 # reinstalls over the old copy
journalctl -u pinlockd -f         # watch the service
```

Preview the lock screen panel without locking (Plasma 6, close it with your
password):

```bash
mkdir -p /tmp/pl/plasma/shells && cp -r data/plasma-shell/* /tmp/pl/plasma/shells/
XDG_DATA_HOME=/tmp/pl PLASMA_DEFAULT_SHELL=io.github.v6bv.pinlock \
    /usr/lib/kscreenlocker_greet --testing
```

**Keep a root shell open while testing PAM changes** (`sudo -i` in a
separate terminal), just in case.

## Layout

```
bin/            thin launchers (pinlock, pinlockd, pinlock-setup)
src/pinlock/
  keymap.py     button names, digits, gamepad detection
  pinstore.py   scrypt PIN storage
  pam.py        adding/removing the PAM block
  daemon.py     pinlockd: buttons -> keystrokes on login/lock screens
  overlay.py    login screen passkey panel (layer-shell, qml/Overlay.qml)
  lockscreen.py turning the lock screen panel on/off for KWin
  cli.py        the pinlock command
  config.py     per-user unlock action
  gui.py        PyQt6 setup app
data/           systemd unit, polkit policy, desktop file, icon
  plasma-shell/ lock screen package; PinPad.qml is the shared panel
packaging/arch  PKGBUILD
tests/          unittest suite
```

## Pull requests

- Keep changes focused, one thing per PR.
- Add or update tests for anything in `pinstore`, `pam` or `cli check`.
- Run `make test` before pushing; CI runs it too.
- Match the existing style: plain Python 3 standard library, plus
  `evdev` and `PyQt6`, and no new dependencies without a good reason.
- Anything that touches authentication gets an extra careful review.
  Explain what changes for the login path.
