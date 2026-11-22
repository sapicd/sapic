# sapic

A self-hosted image host. The backend is an API-only Flask application (`server/`, package name `sapic`);
the front end is a separate Vue 3 single-page app (`web/`). Metadata lives in a relational database
(PostgreSQL / MySQL / SQLite), and **both storage backends and login methods are plugins**: a third-party
pip package can add a new object store or identity provider without touching the core.

[![Actions Status: ci](https://github.com/sapicd/sapic/workflows/ci/badge.svg)](https://github.com/sapicd/sapic/actions?query=workflow%3A%22build+and+test%22)
[![codecov](https://codecov.io/gh/sapicd/sapic/branch/master/graph/badge.svg)](https://codecov.io/gh/sapicd/sapic)
![Last Release](https://img.shields.io/github/release/sapicd/sapic.svg?style=flat-square)
![Version](https://img.shields.io/badge/version-2.0.0--pre-orange.svg?style=flat-square)

> **Current version `2.0.0-pre` (the v2 rewrite)**
>
> The backend is now an API-only Flask app (Peewee + a relational database, no Redis), and the front end
> is a standalone Vue 3 app. The v1 sources are no longer shipped in this repository (see the git tags).
> To upgrade from v1, start with [docs/migrate-v1.md](./docs/migrate-v1.md); the item-by-item changes
> are in [CHANGELOG.md](./CHANGELOG.md).

中文版: [README.md](./README.md).

## Features

- **Upload**: drag and drop, paste, remote URL (fetched by the server, domain names only, redirects are not
  followed), batch queue; per-type suffix and size limits for images and videos, plus optional expiry.
- **Image management**: cursor-paginated lists, keyword and tag filters, batch move / visibility / delete,
  share templates (URL / HTML / Markdown / rST).
- **Albums and visibility**: permissions are per album (public / private / shared), sharing is by username with
  read or write access and an optional expiry, and a single image can override its album.
- **Storage**: multiple backends with priority and replicas; built-in local / Qiniu / Upyun / GitHub / Gitee.
- **Accounts**: registration review, email verification, password reset, OIDC single sign-on; access tokens
  scoped `read` / `upload` / `write` / `admin`.
- **Extensions**: hooks describe their admin UI in declarative JSON; third-party packages can be installed,
  enabled and configured from the admin area, with per-backend settings.
- **Clients**: PicGo / uPic / ShareX / uTools / Typora / a userscript all go through `POST /api/v2/upload`
  with a personal access token.

## Getting started

```bash
git clone https://github.com/sapicd/sapic && cd sapic

# Dependencies: the backend goes into .venv at the repo root, the front end is its own pnpm project
python3 -m venv .venv && ./.venv/bin/python -m pip install -r server/requirements/dev.txt
(cd web && pnpm install)

# Create an admin (sapic_env=dev uses the built-in defaults when server/.cfg is absent)
(cd server && FLASK_APP=sapic sapic_env=dev ../.venv/bin/python -m flask sa create-admin -u admin -p 'your-password')

# Backend on http://127.0.0.1:9514, reloads on code changes
(cd server && FLASK_APP=sapic sapic_env=dev ../.venv/bin/python -m flask run --host 0.0.0.0 --port 9514 --reload)

# In another terminal: front end on http://127.0.0.1:5173 (/api and /raw/ proxy to 9514)
(cd web && pnpm run dev)
```

> The `Makefile` at the repository root is only a convenience wrapper for local development
> (`make setup` / `make dev` / `make web-dev` are equivalent to the commands above). The docs always spell
> out the real commands, so containers and machines without `make` can follow them verbatim.

Single-container Docker (with SQLite):

```bash
docker compose up -d
```

The built-in default secret is long enough to run as-is, but a **public multi-user** deployment should
replace it (the default is public, so anyone with the source can forge session cookies):
`SAPIC_SECRET_KEY=$(openssl rand -hex 32) docker compose up -d`.
Full installation, reverse proxy, container and cluster deployment, and the v1 data migration are covered in
**[docs/deploy.md](./docs/deploy.md)**.

## Documentation

Online docs: Chinese <https://sapic.readthedocs.io/zh-cn/latest/> · English <https://sapic.readthedocs.io/en/latest/>. To build them locally, run
`pip install -r docs/requirements.txt` and then `cd docs && python -m sphinx -b html . _build/html`
(output in `docs/_build/html`). The docs are **bilingual**: Chinese is the source language and the
English translation lives in `docs/locale/en` — preview it with `cd docs && make html-en`.

| Topic | Location |
| --- | --- |
| Introduction and screenshots | [docs/intro.md](./docs/intro.md) |
| Quick start (Docker / source) | [docs/quickstart.md](./docs/quickstart.md) |
| Installation / deployment and operations | [docs/install.md](./docs/install.md), [docs/deploy.md](./docs/deploy.md) |
| Migrating from v1 | [docs/migrate-v1.md](./docs/migrate-v1.md) |
| Quick upload (PicGo / uTools / Typora / context menu / userscript) | [docs/usage.md](./docs/usage.md) |
| `sapicli` command line tool | [docs/cli.md](./docs/cli.md) |
| Configuration | [docs/config.md](./docs/config.md) |
| API reference | [docs/api.md](./docs/api.md) |
| Extension development (hooks, storage drivers, login providers) | [docs/extend/](./docs/extend/index.md) |
| Architecture | [ARCH.md](./ARCH.md) |
| Local development, testing and code style | [docs/dev.md](./docs/dev.md) |
| Backend / front-end internals | [server/README.md](./server/README.md), [web/README.md](./web/README.md) |
| Troubleshooting | [docs/faq.md](./docs/faq.md) |
| Changelog | [CHANGELOG.md](./CHANGELOG.md) |

Upgrading from v1? Read [docs/migrate-v1.md](./docs/migrate-v1.md) first (original SHAs are kept,
so existing links keep working).

## Demo

<https://sapicd.com>, test account `demo` / `123456` (please do not change the password).

It is public: anonymous upload is disabled to keep junk out, registration is open, but please do not use it
for anything beyond testing — images may be removed at any time.

## Security

Please report vulnerabilities privately instead of opening a public issue. Channels, supported versions and
response times are in [SECURITY-en.md](./SECURITY-en.md). 中文版: [SECURITY.md](./SECURITY.md).

## Contributing

Issues and pull requests are welcome. Development conventions, tests and pre-commit checks are in
[docs/dev.md](./docs/dev.md).

<a href="https://github.com/sapicd/sapic/graphs/contributors">
  <img src="https://opencollective.com/sapic/contributors.svg?width=890&button=false" />
</a>

## License

[BSD 3-Clause](./LICENSE)
