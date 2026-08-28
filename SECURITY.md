# Security policy

## What clearmode touches

clearmode runs on Python 3.10 and nothing else. It makes no network calls, and the checker reads files you point it at and writes nothing. It makes no network calls, needs no API key, and sends no telemetry. It runs on Python 3.10 and the standard library, so there is no dependency tree to audit.

`install.sh` writes files into agent config directories you already own. Run `./install.sh --dry-run` first to see every path it would touch. It writes between markers, so it never clobbers content you wrote.

## Reporting a vulnerability

Email e.ghelbur@gmail.com. Include the version, the command, and what happened. Do not open a public issue for a security report.

Expect a reply within 7 days.

## Supported versions

The latest release on `main` is the supported version.
