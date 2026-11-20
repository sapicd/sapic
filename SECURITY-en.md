# Security Policy

中文版: [SECURITY.md](./SECURITY.md).

## Supported versions

| Line | Version | Supported |
| --- | --- | --- |
| v2 (`master`) | `2.0.0-pre.1` and later | Yes |
| v1 (`1.x` tags, `1.16.x`) | `1.16.10` and later | Security fixes only |
| v1 (`1.x` tags) | `1.16.9` and earlier | No — upgrade to `1.16.10` |

Please reproduce issues against the latest release of the line you run before reporting.

## Reporting a vulnerability

**Do not open a public issue, pull request or discussion for a security problem.**

Preferred, in this order:

1. **GitHub private vulnerability reporting** (enabled for this repository). Open the repository page,
   choose the **Security** tab (labelled *Security and quality*), then **Report a vulnerability** next to
   *Security advisories*. The report, the fix and the advisory then stay in one private workspace.
   If that button is not visible, use option 2 instead of opening a public issue.
2. Email **me@tcw.im** with the subject prefix `[sapic security]`. Encrypt with the same address's
   key if you have one; otherwise send the report and we will move it to a private channel.

Note for maintainers: the on/off switch lives in **Settings → Security and quality → Advanced Security →
Private vulnerability reporting** (the button there reads *Disable* when it is on). The **Security →
Advisories → New draft security advisory** page is the publishing side only: it produces the GHSA and the
credits, it does not accept incoming reports, and being able to create a draft says nothing about whether
private reporting is enabled.

Please include:

- affected version, tag or commit (and whether it is v1 or v2),
- the deployment shape you tested (Docker image, bare `flask run`, reverse proxy, database),
- reproduction steps or a proof-of-concept, and the impact you believe it has,
- your name/handle and how you want to be credited in the advisory.

## What to expect

| Stage | Target |
| --- | --- |
| Acknowledgement | within 3 business days |
| Initial assessment (severity, affected lines) | within 10 business days |
| Fix or mitigation released | within 90 days, sooner for high severity |
| Public advisory | after a fixed release, or 90 days after the report |

We follow 90-day coordinated disclosure. If a fix needs more time we will say so and ask for an extension
before the deadline. Reporters are credited in the advisory and in `CHANGELOG.md` unless they ask otherwise.

## Scope

In scope: the code in this repository (backend in `server/`, front end in `web/`, deployment files), and the
official container images built from it.

Out of scope: misconfiguration of your own deployment (for example exposing the admin account, running
without HTTPS in front of a public site, or trusting `X-Forwarded-*` from untrusted peers), vulnerabilities
in third-party hooks packaged separately from this repository, and findings that require an already
compromised server or database.

## Hardening already in place for URL uploads

`POST /api/v2/upload` with the `url` field makes the server fetch a remote object. That path is deliberately
narrow, and these rules are covered by tests (`server/tests/test_images.py`):

- **Domain names only.** Address literals (`http://10.0.0.1/a.png`, `https://[::1]/a.png`, and public IPs
  too) are rejected with `400`. There is nothing to resolve and nothing to check in a literal.
- **Resolved once and pinned.** The host name is resolved a single time, every returned address is checked
  against private / loopback / link-local / reserved / multicast ranges, and the connection is then dialed to
  exactly those addresses. The name is still used for the `Host` header and TLS SNI, so virtual hosting and
  certificate checks are unaffected. A second lookup (the DNS-rebinding time-of-check/time-of-use gap) does
  not happen.
- **No redirects.** A `3xx` answer is reported as `400` and not followed; a redirect would be a second
  request to an address the caller never named. Storage backend read URLs, which sapic builds itself, still
  follow redirects hop by hop.
- **Proxy is administrator-only.** When `upload_fetch_proxy` is configured, only an administrator's upload
  may fall back to it, because a proxied fetch is resolved and connected by the proxy and therefore leaves
  the checks above. Anonymous and regular uploads always connect directly.

## Verifying a fix

The v2 regression tests simulate DNS rebinding deterministically (a stub resolver answers a public address
first and an internal one afterwards) and assert that only the first answer is ever used:

```bash
cd server
python3 -m pytest tests/test_images.py -k "rebinding or redirects or address_literals or proxy" -v
```

Manual checks against a running instance (a regular user token is enough):

```bash
# 1. Address literal: must be rejected before any connection is made.
curl -sS -X POST https://your.site/api/v2/upload \
  -H "Authorization: Bearer $PAT" -F "url=http://127.0.0.1/secret.png"
# -> HTTP 400, {"code": "PARAM_ERROR", "message": "url host must be a domain name"}

# 2. Domain that resolves to a private address: must be rejected after the lookup.
curl -sS -X POST https://your.site/api/v2/upload \
  -H "Authorization: Bearer $PAT" -F "url=http://internal.example.com/secret.png"
# -> HTTP 403, {"code": "FORBIDDEN", "message": "url host is not allowed"}

# 3. Endpoint that answers 302: must not be followed.
curl -sS -X POST https://your.site/api/v2/upload \
  -H "Authorization: Bearer $PAT" -F "url=http://your.site/redirect-to-internal"
# -> HTTP 400, {"code": "PARAM_ERROR", "message": "url redirects are not followed"}

# 4. DNS rebinding: run a lab resolver for one name that answers a public address with TTL 0 and, on the
#    second query, the internal address. With the fix the instance answers 201 only for the public answer
#    (or fails), the internal service never sees a request, and the resolver log shows exactly one query.
```

For the v1 line the same steps apply to `POST /api/upload` (`picbed=http://…`); the fix is described in the
`1.x` security branch and in `CHANGELOG.md` of that branch.

## Acknowledgements

Thanks to the people who reported issues privately and helped make sapic safer. With their permission they
are credited here and in the [changelog](./CHANGELOG.md):

- **Gantrel LLC (Jason Sager)** — reported the missing internal-address check in the v1 URL upload fetch and
  the DNS-rebinding bypass of the v2 check (2026-11), and reviewed the proposed fixes.
