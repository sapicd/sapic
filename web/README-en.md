# sapic web (v2)

The front end of sapic: a Vue 3 + Vite + Element Plus single-page app. It talks to `server/`
**same-origin** — data goes through `/api/v2/*` (uniform envelope `{code, message, data}`), images
through `/raw/<sha>`; in production nginx serves the build output and reverse-proxies those two
prefixes to Flask (the container image already does this, see `docs/deploy.md`).

中文版: [README.md](./README.md).

## Requirements

- Node.js 23+, pnpm 12 (12.23.0 recommended, `corepack enable` is enough)
- The backend running on `127.0.0.1:9514` (run `make dev` at the repository root)

## Development

```bash
pnpm install      # the root make setup installs it as well
pnpm run dev      # http://127.0.0.1:5173
pnpm run build    # build into dist/
pnpm run preview  # preview the build output
```

`vite.config.js` proxies `/api` and `/raw/` to `127.0.0.1:9514` to keep everything same-origin —
that is what makes the cookie session and CSRF work. When the front end lives on a different
domain, set `VITE_API_BASE` to the API prefix (default `/api/v2`).

## Layout

| Path | Contents |
| --- | --- |
| `src/api/client.js` | The only request wrapper: envelope parsing, CSRF header, 401 callback, error normalisation (`errorMessage`) |
| `src/api/messages.js` | Backend English `message` → Chinese dictionary and pattern rules (`localizeMessage`) |
| `src/i18n/` | Bilingual UI catalogues (`zh.js` is the source language, `en.js` the translation) plus `t()` / `setLocale()` |
| `src/stores/session.js` | Current user, CSRF, `authenticated` / `isAdmin` |
| `src/stores/site.js` | Site info (name, background, registration/anonymous upload/plaza switches) from `GET /api/v2/site` |
| `src/router/index.js` | Routes and guards (redirect to login, 404 for unauthorised admin, plaza disabled → home) |
| `src/layout/AppLayout.vue` | Top navigation / full-screen background / footer shell |
| `src/layout/AdminLayout.vue` | Admin sidebar shell: site settings / hooks / storage backends / users |
| `src/components/LocaleSwitcher.vue` | The zh/EN switcher in the top bar |
| `src/components/hook/` | Plugin node rendering: `HookSlot` fetches the node tree per slot, `NodeRenderer` dispatches it recursively |
| `src/components/AvatarCropper.vue` | Avatar cropping |
| `src/views/` | Page components, one per route in the table below |
| `src/utils/format.js` | Display helpers: time (backend timestamps are 10-digit seconds), sizes |
| `public/` | Static assets: `logo.png` / `favicon.png` / default background `background.jpg` |

## Pages

| Route | Component | Notes |
| --- | --- | --- |
| `/` | `UploadView` | Upload: drag and drop / paste / remote URL / queue (`/upload` redirects to the home page) |
| `/images`, `/images/:sha` | `ImagesView`, `ImageDetailView` | Personal library and image details |
| `/albums` | `AlbumsView` | Album management and sharing |
| `/plaza` | `PlazaView` | Public plaza; returns home when the site disables `plaza_enabled` |
| `/settings` | `SettingsView` | Account settings: profile, email, tokens, single sign-on, preferences |
| `/login`, `/register` | `LoginView`, `RegisterView` | Signed-in visitors are sent back to the home page |
| `/admin`, `/admin/setting`, `/admin/hooks`, `/admin/backends`, `/admin/users` | `AdminView` and three more | Admin shell (`AdminLayout`); signed-out users and non-admins always get a 404 |
| Others | `NotFoundView` | 404 |

`requiresAuth` / `requiresAdmin` / `guestOnly` live in the route `meta`; the decision is centralised
in `router.beforeEach`.

## Conventions

The full rules are in the root `AGENTS.md` (front-end conventions section); the key points:

- `<script setup>`; PascalCase components, camelCase functions, and only `let` / `const` for variables
- All requests go through `api/client.js` — never scatter `fetch`; report errors with
  `errorMessage(error, fallback)` instead of `ElMessage.error(error.message)` (backend messages are
  English and must be localised through `messages.js`)
- The UI is **bilingual (Chinese / English)** and does not use `vue-i18n`: strings live in
  `src/i18n/zh.js` (source language) and `src/i18n/en.js` (translation), templates use
  `{{ t('area.key') }}` / `:label="t('area.key')"`, and components never hard-code Chinese;
  Element Plus strings follow `App.vue`'s `<el-config-provider :locale>` (`zh-cn` / `en`)
- Element Plus is imported on demand: write `<el-xxx>` in templates and use `ElMessage` in scripts,
  **do not** import from `element-plus` explicitly
- No business branches in plugin UI: `HookSlot` / `NodeRenderer` only understand the vocabulary the
  backend declares and silently skip unknown types; buttons only call `action`s the backend validated
- String icon names in templates (`icon: 'Brush'` + `<component :is="icon" />`) must be registered in
  `GLOBAL_ICONS` in `src/main.js`, otherwise the icon is silently missing
- Render videos with a native `<video>` based on `images.is_video` (use `muted preload="metadata"` in
  lists to show the first frame as the cover); never render videos with `el-image`

## Build and deployment

`pnpm run build` produces `dist/`; serve it from a static server that also reverse-proxies `/api` and
`/raw/` to the backend. The container image already performs this step at build time, so **the front
end does not need to be deployed separately** (see the container and orchestration section in
`docs/deploy.md`).
