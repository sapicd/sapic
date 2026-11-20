# sapic server (v2)

The sapic v2 backend, API-only (the front end is a separate Vue application).

Chinese version: [README.md](./README.md).

## Requirements

- Python 3.10+
- One of three databases: **SQLite** (default, zero configuration, single instance only),
  **PostgreSQL** (recommended for multiple processes / replicas), or **MySQL 8**

## Installing dependencies

This package is **local only** — it is not published to PyPI and must not be `pip install`-ed;
dependencies live in `requirements/` inside this directory. Run from the **repository root**:

```bash
# Backend only (run inside server/)
python -m pip install -r requirements/dev.txt

# Development + test dependencies + front-end dependencies (from the repository root;
# the Makefile's `make setup` is equivalent to this line)
python -m pip install -r server/requirements/dev.txt && (cd web && pnpm install)
```

## Configuration

Values are resolved in this order: configuration class defaults (`basis/conf.py`) → `server/.cfg`
(`key=value`) → environment variables (`sapic_` prefix), and every value is validated after loading.
`sapic_env=dev` (or `FLASK_ENV=development`) selects `DevConfig` (debug mode and DEBUG logging).

| Option | Description | Default |
| --- | --- | --- |
| `sapic_env` | Runtime environment; `dev`/`development` enables development mode | `production` |
| `sapic_db_url` | Database DSN, e.g. `postgresql://user:pass@host:5432/sapic`, `mysql://...`, `sqlite:///tmp/sapic.db` | `sqlite:///<server>/data/sapic.db` |
| `sapic_secretkey` | Web application secret (at least 14 bytes); **optional**, an empty value falls back to the built-in default (a public string, replace it for public multi-user deployments) | built-in random string |
| `sapic_maxupload` | Upper bound for the whole upload request (MB, mapped to `MAX_CONTENT_LENGTH`); must exceed the per-file image/video limits configured for the site | `25` |
| `sapic_storagedir` | Local storage directory | `data/upload` |
| `sapic_external_base_url` | Public base URL used to build image links | empty (relative URLs) |
| `sapic_proxyfix` | Whether to trust proxy headers | off |

There are also `sapic_session_ttl` (session lifetime, 7 days by default), `sapic_loglevel`
(`INFO` by default), `sapic_hookpkgstoragedir` (third-party hook package directory, `data/hooks` by
default), `sapic_hookmarketurl` and `sapic_updatecheckurl` (leave empty to disable the outbound
update check); see `docs/config.md` for the complete list.

## Database initialisation

Table creation and incremental migrations (including `ALTER`) run automatically at startup, so no
manual step is needed; concurrent startup of several workers is handled by retries plus idempotent
migrations. Run these only as a manual fallback:

```bash
cd server
export FLASK_APP=sapic
flask sa upgrade          # create tables / incremental migrations (already run at startup)
flask sa create-admin -u admin -p 123456
flask sa purge-expired    # purge expired images manually (requests also sweep them, throttled)
```

## Running

```bash
cd server
flask run --host 0.0.0.0 --port 9514
```

Use gunicorn in production:

```bash
gunicorn "sapic:create_app()" -b 0.0.0.0:9514 -w 4 -k gevent
```

## API overview

| Method | Path | Description |
| --- | --- | --- |
| GET | `/api/v2/health` | Health check (database) |
| POST | `/api/v2/auth/register` | Register |
| POST | `/api/v2/auth/login` | Log in (cookie session, returns the CSRF token) |
| POST | `/api/v2/auth/logout` | Log out |
| GET | `/api/v2/auth/session` | Current session |
| POST | `/api/v2/auth/password/forgot` | Send a reset token (valid for 10 minutes) |
| POST | `/api/v2/auth/password/reset` | Reset the password with a token |
| PUT | `/api/v2/auth/password` | Change the password (revokes the other sessions) |
| GET/POST | `/api/v2/auth/tokens` | List / create PATs (`scopes` accepts `read`/`upload`/`write`/`admin`, defaulting to the first three) |
| DELETE | `/api/v2/auth/tokens/<id>` | Revoke a PAT |
| GET | `/api/v2/auth/oidc/<name>` | Start single sign-on (`?bind=1` binds it to the current account) |
| GET | `/api/v2/auth/oidc/<name>/callback` | Single sign-on callback |
| GET | `/api/v2/auth/identities` | Linkable login methods and their binding state |
| DELETE | `/api/v2/auth/identities/<name>` | Unbind (requires the current password) |
| POST | `/api/v2/auth/email/verify`, `/email/confirm` | Resend the verification token / submit a token to mark the address verified |
| POST | `/api/v2/auth/avatar` | Upload an avatar (cropped server-side); `PUT /auth/profile` changes the nickname and email |
| DELETE | `/api/v2/auth/account` | Self-service deletion (requires the current password; 409 while images remain) |
| POST | `/api/v2/upload` | Upload (multipart, field `file` or `url`, optional `expire` in seconds and `album_id`); `url` is fetched by the server and falls back to the site setting `upload_fetch_proxy` when a direct connection fails |
| GET | `/api/v2/images` | Image list (cursor pagination, permission filtered) |
| POST | `/api/v2/images/import` | Register external links in bulk (no download; `items` is an array of URLs, optional `album_id`) |
| POST | `/api/v2/images/batch/delete` | Batch delete (`shas`, at most 100) |
| PATCH | `/api/v2/images/batch` | Batch update: `album_id` / `visibility` / `plaza` / `tags` |
| GET/PATCH/DELETE | `/api/v2/images/<sha>` | Details / update (including the `expire_at` expiry) / delete |
| GET/POST | `/api/v2/albums` | List / create albums |
| PATCH/DELETE | `/api/v2/albums/<id>` | Update / delete (non-empty albums are refused) |
| GET/POST | `/api/v2/albums/<id>/shares` | List / add members (username + `permission` + optional `expires_in`) |
| PATCH/DELETE | `/api/v2/albums/<id>/shares/<uid>` | Change permission and expiry / remove a member |
| GET/POST | `/api/v2/backends` | List / create storage backends (admin only) |
| PATCH/DELETE | `/api/v2/backends/<id>` | Change priority, enable/disable, override configuration per backend / delete (409 while replicas exist) |
| GET | `/api/v2/site` | Public site info (name, background, registration / anonymous upload / plaza switches) |
| GET | `/api/v2/plaza` | Image plaza (anonymous; 404 when `plaza_enabled` is off) |
| GET/PUT | `/api/v2/settings` | Read / update site settings (admin only) |
| GET | `/api/v2/settings/version` | Update check (admin only, 24h in-process cache) |
| POST | `/api/v2/settings/smtp/test` | Send a test email (admin only) |
| GET/PATCH/DELETE | `/api/v2/users`, `/users/<id>` | User list (`page`/`page_size`) / review, disable, grant admin / hard delete (admin only) |
| GET/POST/PATCH/DELETE | `/api/v2/hooks*` | Hook list, configuration, enable/disable, reload, market and package management (admin only) |
| GET | `/raw/<sha>` | Read an image (public images 302 to the backend URL; private ones are served after authorisation, Range supported) |
| GET | `/api/v2/userscript.user.js` | Userscript (Tampermonkey/Violentmonkey), login required; gated by the personal setting `userscript_enabled`, installable with `?token=` (`upload` scope) |
| GET/PUT | `/api/v2/auth/settings` | Personal preferences: `userscript_enabled` / `bg_image` / `bg_image_mobile` / `bg_opacity` |

This list only covers the main endpoints; **parameters, response fields and error codes are in the
online documentation served by each instance** (`GET /api/v2/docs`, source `GET /api/v2/openapi.json`),
and the cross-endpoint conventions, authentication and business rules are in `docs/api.md` at the
repository root. Every response uses the envelope `{code, message, data}`; on failure `code` is an
`ErrorCode` from `basis/errors.py`.

Authentication: cookie session (writes require `X-CSRF-Token`) or `Authorization: Bearer <PAT>`.

Single sign-on (OIDC, provided by the `passport` hook):

- Login order: an already bound identity logs in directly; an unbound identity whose provider has a
  verified email matching a locally verified account is linked automatically; otherwise an account is
  created from the provider data (the main entry point for new users, creating a default album too).
- A new account takes the provider's stable identifier as its local username (for Passport that is
  `sub`/uid, 22 lowercase characters); the nickname is only stored as the display name in `nickname` —
  nicknames can change and repeat, so they must not be used as account names.
- Email linking is always enabled and requires **both the provider and the local account to have a
  verified email**: a provider without `email_verified` is treated as verified, while an explicit
  `false` prevents linking; the local address must complete the verification flow first, so an account
  that "squatted" somebody else's email cannot be taken over.
- Email verification: a token is sent automatically on registration and can be resent from the
  account settings (`POST /api/v2/auth/email/verify`); submitting the token to
  `POST /api/v2/auth/email/confirm` marks the address verified. Changing the email resets it to
  unverified and invalidates the old token. Password recovery (`/auth/password/forgot`) also only
  issues tokens for verified addresses.
- Signed-in users can bind/unbind an identity in "Account settings → Single sign-on"; unbinding
  requires the current password so an OIDC-only account (random password) cannot lock itself out.
- Turning the site setting `password_login` off disables password login and local registration
  together, leaving single sign-on as the only way in.

The image list (`GET /api/v2/images`, login required) is a personal library: it only returns your own
images and the albums shared with you — other people's public images never appear there (public
exposure goes through the plaza and must be published explicitly); anonymous requests get a 401.
Public images remain directly accessible through `src` / `/raw/<sha>`.

Image URL (`src`) policy:

- **Public images**: return a direct URL to the storage backend with the highest priority; traffic does
  not go through sapic. That URL comes from what the `upimg_save` hook returns: the backend's CDN
  domain (`domain`) when configured; local storage falls back to the proxy, GitHub/Gitee fall back to
  `download_url` (GitHub also falls back to jsDelivr).
- **Private images** (a private album, or a single image overriding `visibility=private`): always
  return `/raw/<sha>` and let sapic authorise and serve it; remote replicas are streamed through so
  the origin address is never exposed.
- **Backends without a direct URL** (e.g. local storage without `domain`): fall back to `/raw/<sha>`,
  streaming the local replica with Range support.
- **Caching**: public images use `Cache-Control: public, max-age=31536000, immutable`; private images
  use `private, max-age=31536000, immutable` (browser-only, shared caches must not store them).

Storage keys look like `{user}/{year}/{month}/{day}/{ASCII filename}-{sha fragment}.{ext}`: the suffix
keeps same-named files from overwriting each other. File names are normalised through
`secure_filename` (non-ASCII characters such as Chinese are dropped); when the stem ends up empty it
falls back to `{yyyyMMddHHmmss}{6 random characters}`, always keeping the extension. Deletion runs
against `ImageBackend.object_key`.

Media metadata: uploads only read `width`/`height` from the file header (no imaging library, no pixel
decoding) and **strip EXIF/XMP** before writing (JPEG APP1, PNG `eXIf`/XMP text chunks, WebP
`EXIF`/`XMP ` chunks), so capture time, camera and GPS never reach the stored object; GIF/BMP/ICO/SVG
and videos are stored as-is.

Image expiry: pass `expire` in seconds when uploading (`0` or omitted = site default, permanently by
default) and adjust it later with `expire_at` (a second-level timestamp; `null` clears it) on
`PATCH /images/<sha>`. Once expired an image is immediately treated as missing (`/raw/<sha>`, details,
lists and the plaza all 404 or drop it) and is **hard deleted** in the background (object files,
replicas and the record). The sweep runs throttled during requests (at most one batch every 5 minutes
per process) and can also be scheduled through `flask sa purge-expired`. The site settings
`image_expire_default_days` and `image_expire_max_days` control the default lifetime and the upper
bound (once the latter is set, permanent images are no longer allowed).

Userscript (`GET /api/v2/userscript.user.js`, login required): generates a Tampermonkey/Violentmonkey
script per user that uploads an image to this site with **Alt (or Ctrl) + click** on any page. Uploads
use the `url` field of `POST /api/v2/upload` (fetched server-side, bypassing browser CORS) and the
script source **contains no token**: the first upload asks for a PAT with only "upload images" ticked,
keeps it in userscript storage, and the script menu can replace it at any time. Whether the script can
be installed is governed by the personal setting `userscript_enabled` (off by default) — once off, the
install/update URL immediately returns 404. The install URL also accepts `?token=<PAT>`
(`upload` scope) for clients that cannot carry cookies.

Image plaza (`GET /api/v2/plaza`, anonymous):

- The plaza is an **exposure channel** and changes no permissions: `visibility` still decides who can
  see an image, and only images whose effective visibility is `public` appear in the list.
- Publishing is explicit: the album-level switch `albums.plaza` and the three-state `images.plaza`
  (`NULL` follows the album, `true` forces publication, `false` forces exclusion).
- The site setting `plaza_enabled` is **off by default** (a personal image host needs no public
  exposure channel, and public UGC brings moderation work); only when it is on does
  `GET /api/v2/plaza` work — when off the endpoint 404s and every plaza entry point in the front end
  disappears with it.
- Migration `v005 plaza` adds both columns; existing images stay off the plaza by default.

## Current scope

- Done: application factory, Peewee models and the migration framework, health check,
  register/login/password recovery/email verification/OIDC/PAT, upload and serving, image expiry and
  batch operations, album permissions and share members, storage backend management and replicas, the
  image plaza, the userscript, SMTP configuration and test email, admin user management, the update
  check, and third-party hook package installation plus the market.
- Pending: upload tickets (the model exists but has no API/UI), replica reconciliation and automatic
  backfill, and the API/UI for user-defined storage backends (the data layer exists as
  `scope="user"` plus the site switch `allow_user_backends`).

Storage backends: enabled storage hooks (`catalog=upload`) automatically add a `storage_backends` row
at startup and whenever a backend is resolved; credentials come from the hook configuration and can be
overridden per backend. Uploads go to the enabled backend with the lowest `priority`; a backend that
still holds replicas cannot be disabled or deleted, and deleting the last row of a driver is the same
as disabling that hook (otherwise the next sync recreates it).

## Tests

```bash
cd server
python -m pytest -q
```

Tests use a temporary SQLite database and need no external database; CI
(`.github/workflows/ci.yml`) runs Python 3.10 and 3.12 plus one front-end build job. When a change
touches database dialects (indexes, JSON fields, `ALTER`), verify it manually against
PostgreSQL / MySQL as well.
