# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] - 2026-11-17

First release.

### Added

- `pinlockd`: turns controller buttons into PIN digits on the login and lock
  screens, and only there.
- PAM hookup for Plasma Login Manager, SDDM, LightDM, GDM and the KDE lock
  screen (`pinlock pam enable` / `pinlock pam disable`). The normal password
  keeps working.
- Salted scrypt PIN storage in `/etc/pinlock`, covered by the system's
  faillock lockout.
- Optional action after a controller unlock: Steam Big Picture (default), a
  custom command, or nothing.
- Xbox-style passkey panel: an overlay in the bottom-left of the login
  screen that appears on the first button press, and an optional lock screen
  version (`pinlock lockscreen enable`, or the toggle in the setup app).
- `pinlock-setup`, a controller-friendly PyQt6 app to set or change the PIN,
  test the controller, pick the unlock action and remove the PIN.
- `pinlock` command line: `status`, `test`, `set`, `remove`, `pam`,
  `lockscreen`.
- Makefile install, `install.sh` / `uninstall.sh`, and an Arch PKGBUILD.

[Unreleased]: https://github.com/v6Bv/pinlock/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/v6Bv/pinlock/releases/tag/v0.1.0
