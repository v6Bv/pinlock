# Security policy

pinlock plugs into how people log in, so security reports are very welcome.

## Reporting a vulnerability

**Please don't open a public issue.** Report it privately through
[GitHub's private vulnerability reporting](https://github.com/v6Bv/pinlock/security/advisories/new).

Please include:

- what an attacker can do, and what they need first (physical access,
  a local account, a running session, …)
- steps to reproduce
- your distro, login screen and pinlock version (`pinlock --version`)

You'll get a reply within a week. Fixes are released as soon as they're
ready, and you're credited in the release notes unless you'd rather not be.

## Scope

In scope:

- getting past the login or lock screen without the PIN or password
- reading or changing another user's PIN
- `pinlockd` typing input outside the login/lock screens
- privilege escalation through `pinlock`, `pinlockd` or the polkit action

Expected behavior, not a vulnerability:

- A PIN is a short password. Brute-forcing it is limited only by the
  system's faillock settings (3 tries, then a 10-minute lockout, by default).
- Your own PIN hash is readable by your own group, so code running as you
  can brute-force it offline.
- A PIN typed on the keyboard works the same as one typed on a controller.

## Supported versions

Only the latest release gets security fixes.
