# Security policy

## Reporting a vulnerability

Please **do not open a public issue** for security problems. Instead, open a private security
advisory on GitHub (Security → Advisories → Report a vulnerability) or email the maintainer.

Include:

- affected version / commit,
- Windows version,
- step-by-step reproduction,
- impact (e.g., data leakage, local privilege, extension issue),
- any suggested fix.

We aim to acknowledge within 72 hours and to publish a fix + advisory as soon as possible.

## Scope

WorkTime is a local-first tool. In scope:

- unintended network access,
- data written outside the app folder,
- privilege escalation / UAC bypass,
- clipboard or content captured beyond documented limits,
- extension permissions or token leakage,
- unsafe handling of untrusted input (window titles, page text, clipboard).

Out of scope:

- “the tool records window titles/clipboard” — that is its documented purpose, fully local and
  user-controlled.
- Antivirus/SmartScreen warnings caused by unsigned builds (tracked as packaging work).

## Data handling

- No telemetry, no auto-update, no remote endpoints.
- HTTP services bind `127.0.0.1` only and require a per-install token for ingest.
- Clipboard is stored as hash + first 240 characters; password managers are excluded.
- Raw data retention is configurable and defaults to 30 days (clipboard 7 days).

## Supported versions

Only the latest release receives security fixes (prototype phase).
