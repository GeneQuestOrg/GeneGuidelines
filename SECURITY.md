# Security policy

If you find a security issue, **please do not open a public GitHub issue**.

Email the maintainer at **darek@genequest.org** with:

- A description of the issue
- Steps to reproduce
- Suggested fix, if known

We aim to acknowledge reports within 72 hours and to ship a fix or
mitigation within a reasonable window depending on severity.

Coordinated disclosure is appreciated. If your report is sensitive,
please indicate that and we will agree on a disclosure timeline.

## Supported versions

This is pre-1.0 software under active development. Only the latest
commit on the `main` branch is supported for security fixes. Older
tags may not receive patches.

## Out of scope

- Vulnerabilities in third-party dependencies (please report upstream).
- Issues that require user-controlled environment access (`.env`
  contents, local filesystem, etc.).
- Rate-limiting or DoS issues — the project does not yet expose a
  hardened production service.
