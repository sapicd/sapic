# Security Policy

Chinese version: [SECURITY-cn.md](./SECURITY-cn.md).

## Supported versions

| Line | Version | Supported |
| --- | --- | --- |
| v1 (`1.x` tags) | `1.16.10` and later | Yes |
| v1 (`1.x` tags) | `1.16.9` and earlier | No — upgrade to `1.16.10` |
| v2 (`master`, `2.x`) | `2.0.0-pre.1` and later | Yes |

Please reproduce issues against the latest release of the line you run before reporting.

## Reporting a vulnerability

**Do not open a public issue, pull request or discussion for a security problem.**

Preferred, in this order:

1. GitHub private vulnerability reporting — open the repository's **Security** tab and choose
   *Report a vulnerability*. This keeps the report, the fix and the advisory in one place.
2. Email **me@tcw.im** with the subject prefix `[sapic security]`. Encrypt with the same address's
   key if you have one; otherwise send the report and we will move it to a private channel.

Please include:

- affected version, tag or commit (and whether it is v1 or v2),
- the deployment shape you tested (Docker image, bare `flask run`, reverse proxy, Redis),
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
before the deadline. Reporters are credited in the advisory and in `docs/changelog.rst` unless they ask
otherwise.

## Scope

In scope: the code in this repository (`src/` backend, templates, deployment files), and the official
container images built from it.

Out of scope: misconfiguration of your own deployment (for example exposing the admin account, running
without HTTPS in front of a public site, or trusting `X-Forwarded-*` from untrusted peers), vulnerabilities
in separately packaged third-party hooks, and findings that require an already compromised server or Redis.

## Hardening already in place for URL uploads

`POST /api/upload` with a `picbed` value starting with `http(s)://` makes the server fetch a remote object.
That path is deliberately narrow (`utils/netguard.py`), and these rules are covered by tests
(`src/tests/test_netguard.py`):

- **Domain names only.** Address literals (`http://10.0.0.1/a.png`, `https://[::1]/a.png`, and public IPs
  too) are refused. There is nothing to resolve and nothing to check in a literal.
- **Resolved once and pinned.** The host name is resolved a single time, every returned address is checked
  against private / loopback / link-local / reserved / multicast ranges, and the connection is then dialed to
  exactly those addresses. The name is still used for the `Host` header and TLS SNI, so virtual hosting and
  certificate checks keep working. A second lookup (the DNS-rebinding time-of-check/time-of-use gap) does not
  happen.
- **No redirects.** A `3xx` answer is an error and is not followed; a redirect would be a second request to
  an address the caller never named.
- **Proxy is administrator-only.** When a fetch proxy is configured (`proxies` in the site settings), only an
  administrator's upload may fall back to it, because a proxied fetch is resolved and connected by the proxy
  and therefore leaves the checks above. Anonymous and regular uploads always connect directly.
- **Size capped.** The body is read with a limit of the configured maximum upload size.

## Verifying a fix

The regression tests simulate DNS rebinding deterministically (a stub resolver answers a public address first
and an internal one afterwards) and assert that only the first answer is ever used:

```bash
cd src
python3 -m unittest tests.test_netguard -v
```

Manual checks against a running instance (a regular user token is enough):

```bash
# 1. Address literal: must be refused before any connection is made.
curl -sS -X POST https://your.site/api/upload \
  -H "Authorization: Token $TOKEN" -F "picbed=http://127.0.0.1/secret.png"
# -> upload fails with an error, the internal service sees no request

# 2. Domain that resolves to a private address: must be refused after the lookup.

# 3. Endpoint that answers 302: must not be followed, even to a public target.

# 4. DNS rebinding: run a lab resolver for one name that answers a public address with TTL 0 and, on the
#    second query, the internal address. With the fix the upload only ever uses the first answer (or fails),
#    the internal service never sees a request, and the resolver log shows exactly one query.
```

The v2 line (`master`) uses the same rules; its checks are described in `server/sapic/libs/images.py` and
`server/tests/test_images.py` of that branch.

## Acknowledgements

Thanks to the people who reported issues privately and helped make sapic safer. With their permission they
are credited here and in the [changelog](./docs/changelog.rst):

- **Gantrel LLC (Jason Sager)** — reported the missing internal-address check in the v1 URL upload fetch and
  the DNS-rebinding bypass of the v2 check (2026-11), and reviewed the proposed fixes.
