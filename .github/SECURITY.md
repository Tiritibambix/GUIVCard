# Security policy

## Scope and expectations

GUIVCard is a web interface to a CardDAV server, designed for local or
trusted-network use. It has no user accounts of its own: authentication is
delegated to the CardDAV server, and the password lives in the app process's
memory for the length of a session, never on disk.

Exposing the app to the public internet without an additional access-control
layer (a reverse proxy with authentication, a VPN) is outside the threat model.
Reports that rely only on it being publicly reachable will be acknowledged but
are not treated as vulnerabilities.

## Reporting a vulnerability

Please report privately rather than opening a public issue:

- Use GitHub's [private vulnerability reporting](https://github.com/Tiritibambix/GUIVCard/security/advisories/new).

Useful details: the version or image tag, the CardDAV server and version, what
an attacker can reach, and the steps to reproduce it.

Expect an acknowledgement within a week. As a hobby project maintained in spare
time, there is no guaranteed fix window; the severity and the fix will be
discussed in the advisory.

## What is in scope

- Reading or writing another user's contacts.
- Recovering a CardDAV password from the browser, the logs, or a response.
- Bypassing authentication, CSRF protection, or the session's expiry.
- Server-side request forgery through the configured CardDAV URL.
- Injection into a stored contact that executes in another user's browser.

## What is not

- Anything requiring the operator's own `SECRET_KEY` or shell access.
- Denial of service through a deliberately large upload beyond the configured
  limit, which `MAX_CONTENT_LENGTH` bounds rather than prevents.
- Missing hardening on a deployment that does not set `SECURE_COOKIES` behind
  HTTPS, which is documented in the README.
