# Contributing

Thanks for taking the time to contribute. Chinese version: [CONTRIBUTING-cn.md](./CONTRIBUTING-cn.md).

## Security issues

Please **do not** open a public issue, pull request or discussion for a vulnerability. Report it privately
through the channels in [SECURITY.md](./SECURITY.md).

## Bug reports

Open an [issue](https://github.com/sapicd/sapic/issues/new) and include:

- what actually happened, plus the full traceback when there is one;
- a minimal, complete and verifiable example if you can — it also shows whether the problem is in your own
  deployment rather than in sapic;
- versions of Python, the database and sapic (`GET /api/v2/health` reports the version and the database
  status), and the configuration that matters (mask secrets before posting).

The effective backend configuration can be printed with:

```bash
make config
```

## Feature requests

Open an [issue](https://github.com/sapicd/sapic/issues/new) as well and describe the use case, not only the
mechanism you have in mind. A pull request is very welcome.

## Pull requests

**Before you start**

- Fork <https://github.com/sapicd/sapic> and keep your fork in sync
  ([Syncing a fork](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/working-with-forks/syncing-a-fork)).
- Branch from `dev` and open the pull request against `dev`, not `master`.

**Environment**

```bash
make setup          # backend dev requirements into .venv + pnpm install for the front end
make dev            # backend on 0.0.0.0:9514, reloads on change
make web-dev        # front end on 127.0.0.1:5173, proxies /api and /raw/ to 9514
```

These targets only wrap the real commands (they assume a repo-root `.venv` and a machine with `make`).
Installation, containers and reverse proxies are covered in [DEPLOY.md](./DEPLOY.md).

**Code**

Follow the conventions in [docs/dev.md](./docs/dev.md), in short:

- PEP 8, 4-space indents, `# -*- coding: utf-8 -*-` plus an English module docstring, imports at the top
  (standard library → third party → project).
- Python 3.10+ syntax, type annotations on new functions (`str | None`, `dict[str, Any]`).
- Failures use `ApiError(message, code)` with an English message; no bare `except:`; log through
  `logging.getLogger(__name__)` instead of `print()`.
- Respect the dependency direction `views → libs/utils → models/basis`, and keep web-only helpers in
  `utils/web.py`.
- Database changes go through an idempotent migration in `server/sapic/migrations/`; never call
  `create_tables()` to change an existing structure.
- A new setting must be wired into both the admin form and the place where it takes effect.

**Tests**

```bash
make test           # or: cd server && python -m pytest -q
```

Tests use a temporary SQLite database, so no external service is needed. CI runs Python 3.10, 3.12 and 3.13;
please make sure new behaviour (especially extension contracts, parsers and permission checks) is covered.

**Documentation**

```bash
make docs           # Sphinx build into docs/_build/html, warnings are errors
```

New pages must be registered in the `toctree` of `docs/index.md`, otherwise they are never built.

**Changelog and version**

Add a concise entry to [CHANGELOG.md](./CHANGELOG.md) and bump `server/sapic/version.py` in the same pull
request. Keep the entry to what a user can observe; implementation details and internal helper names do not
belong there.

**Commits and the pull request**

- Use conventional-commit subjects such as `fix(images): keep the album on re-upload` or
  `docs: split the readme by language`.
- Keep unrelated changes out of the commit; one topic per pull request is easiest to review.

## Extensions

Storage backends, login providers and other hooks are ordinary pip packages that talk to sapic through the
contracts described in [docs/extend/](./docs/extend/index.md). Publish yours on PyPI and open an issue if you
want it listed in the built-in hook market.

## License

By contributing you agree that your work is licensed under the [BSD 3-Clause](./LICENSE) license.
