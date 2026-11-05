# sapic v2 架构文档

本文描述 sapic v2 的运行时组成、代码分层、数据模型与扩展点。部署步骤见 [DEPLOY.md](./DEPLOY.md)，
编码约定见 [AGENTS.md](./AGENTS.md)；v1 代码只作存档（`V1/`），不参与构建。

## 1. 定位

- **API-only 后端 + 独立前端**：`server/` 只提供 `/api/v2/*` 与 `/raw/<sha>`，`web/` 是独立的
  Vue 3 SPA，两者通过 HTTP 同源交互，生产环境由同一个 nginx 站点提供服务。
- **Peewee ORM + 真实数据库**（PostgreSQL / MySQL / SQLite 三选一），不再像 v1 那样以 Redis 为主存储；
  Redis 变成可选组件（当前仅用于健康检查探活）。
- **存储后端插件化**：图片落到哪个后端由「驱动钩子 + backend 配置 + 副本」决定，新增驱动不需要改核心代码。
- 当前版本：`server/sapic/version.py` 的 `__version__`。

## 2. 运行时组件

```
                    ┌──────────────────────────────────────────┐
  浏览器 ──HTTPS──▶ │ nginx                                    │
                    │  /        → web/dist（SPA，try_files）    │
                    │  /api/v2  → 127.0.0.1:9514（gunicorn）    │
                    │  /raw/    → 127.0.0.1:9514               │
                    └───────────────┬──────────────────────────┘
                                    │ WSGI
                    ┌───────────────▼──────────────────────────┐
                    │ gunicorn（gevent workers，可多实例）       │
                    │  Flask app（create_app 工厂）             │
                    │   ├─ Peewee → PostgreSQL/MySQL/SQLite    │
                    │   ├─ Redis（可选，仅探活）                 │
                    │   └─ 存储驱动钩子 → 本地目录 / 对象存储     │
                    └──────────────────────────────────────────┘
```

要点：

- **无状态**：登录态放在签名 Cookie 里（`sapic_sid`），服务端不存会话，所以可以随意加 worker / 加实例。
- **启动即迁移**：`create_app()` 内部调用 `migrations.auto_upgrade()`，多 worker 同时启动时会串行化并在
  锁冲突时重试，因此发布新版本不需要单独执行迁移（`flask sa upgrade` 只是运维兜底）。
- **静态资源**：后端不托管前端构建产物，`web/dist` 交给 nginx / CDN。

## 3. 代码分层

```
server/sapic/
├── __init__.py        create_app()：配置 → DB → 迁移 → 认证 → 钩子 → 蓝图 → 错误处理
├── version.py         __version__
├── cli.py             flask sa upgrade / create-admin
├── basis/             基础设施（不依赖业务）
│   ├── common.py      as_bool / as_int / is_dev
│   ├── conf.py        配置类 + load_config()（默认值 ← .cfg ← 环境变量 → 校验）
│   ├── db.py          Peewee DatabaseProxy / Redis 客户端 / 请求级连接生命周期
│   ├── errors.py      ApiError / ErrorCode / errorhandler
│   └── vars.py        BASE_DIR / ENV_PREFIX / Cookie 名 / 常量
├── libs/              与 Web 无关的业务封装
│   ├── auth.py        Cookie 会话、PAT（scopes）、CSRF、login_required / admin_required
│   ├── users.py       注册、认证、OIDC 建号、资料、purge_user
│   ├── albums.py      相册、默认/系统相册、共享授权
│   ├── images.py      图片生命周期：创建、查询、可见性、删除、远程抓取
│   ├── storage.py     backend 解析、驱动调用（upimg_save / upimg_delete）、副本
│   ├── hook.py        HookManager：清单聚合、插槽渲染、动作、数据集、热加载
│   ├── ui.py          声明式 UI 词表与清洗（唯一可信来源）
│   ├── settings.py    站点设置读写（settings 表 + DEFAULTS）
│   └── mail.py        邮件投递
├── models/            Peewee 模型（BaseModel + 各表）
├── migrations/        版本化迁移（MIGRATIONS 列表，必须幂等）
├── utils/
│   ├── common.py      纯工具（游标编解码等，无 Flask 上下文）
│   └── web.py         响应信封 ok()、游标分页 paginate()、签名 Cookie 读写
├── views/             蓝图与路由（薄封装）
└── hooks/             内置钩子，一个 .py 一个插件
```

**依赖方向单向**：`views → libs/utils → models/basis`。

- `utils/web.py` 依赖 Flask 上下文，禁止被非 Web 模块导入；
- `libs/hook` 依赖 `libs/ui` 做节点清洗；
- `hooks/*` 只被 `libs/hook` 按需导入，禁止反向依赖业务层；
- 通用函数放 `libs/`，纯工具放 `utils/common.py`，依赖 `request`/`g` 的放 `utils/web.py`。

## 4. 请求生命周期

1. `before_request`：生成/透传 `X-Request-Id`（`g.request_id`），按需打开数据库连接。
2. 认证装饰器（`login_required` / `admin_required`）解析凭据：
   - `Authorization: Bearer sp_...`（PAT）→ `ApiToken.token_hash` 查表 → 校验过期/吊销/账号状态 → 得到 `scopes`；
   - 否则读签名 Cookie `sapic_sid`（`{uid, sv, csrf}`）→ `User.session_version == sv` 才算有效会话。
3. 视图只做参数解析与鉴权，业务下沉到 `libs/`。
4. 响应统一由 `utils/web.ok()` 包成 `{"code": "OK", "message": "", "data": ...}`；异常走
   `ApiError`（`code` 为 `ErrorCode` 名、`message` 为英文）或 `HTTPException` 的 `errorhandler`。
5. `after_request`：回写 `X-Request-Id`，必要时下发/清除 Cookie。

### API 约定

| 项 | 约定 |
| --- | --- |
| 前缀 | `/api/v2`（`views/__init__.API_PREFIX`），`public` 蓝图例外，直接挂 `/raw/<sha>` |
| 成功信封 | `{"code": "OK", "message": "", "data": {...}}` |
| 失败信封 | `{"code": <ErrorCode>, "message": "<英文>", "data": null}` |
| 列表分页 | 游标分页，`?limit=&cursor=`，返回 `items / next_cursor / has_more / limit`，按 `(created_at, id)` 倒序 |
| 写操作鉴权 | Cookie 会话需 `X-CSRF-Token`；PAT 按 scope（`read`/`upload`/`write`/`admin`）限制 |

主要端点：`auth/*`（登录、注册、OIDC、PAT、邮箱）、`uploads`、`images`、`albums`（含 shares）、
`plaza`、`settings`（管理员）、`users`（管理员）、`hooks`（管理员的动作与数据集）、`site`（公开站点信息）、
`health`。完整清单见 `server/README.md`。

## 5. 数据模型

| 表 | 作用 | 关键点 |
| --- | --- | --- |
| `users` | 账号 | `username` 唯一且不可改（参与上传路径）；`session_version` 自增即吊销全部会话；`oidc_issuer`+`oidc_subject` 联合唯一 |
| `user_settings` | 个人设置 | `(user, key)` 唯一 |
| `albums` | 相册 | `owner_id` 可空（系统相册）；`is_default` 标记兜底相册；`visibility` / `plaza` |
| `album_shares` | 相册共享 | `(album, grantee)` 唯一，`permission` = `read`/`write`，`expires_at` 过期即失效 |
| `images` | 图片元数据 | `sha` 是公开标识；`visibility` 为空表示跟随相册；`plaza` 三态；`source_url` 非空表示外链登记（不下载、无副本）；软删除用 `status`/`deleted_at` |
| `storage_backends` | 存储后端实例 | `hook_name` 指向驱动钩子；`scope` = `system`（管理员维护默认存储）/`user`（用户自定义，`owner_id` 非空）；`priority` 越小越优先 |
| `user_backends` | 用户可用后端 | 授权 + 个人排序；无授权记录表示不限制 |
| `image_backends` | 副本 | 一张图在一个后端一条记录，`object_key` 用于删除 |
| `api_tokens` | PAT | 只存 `token_hash`，`scopes` 为 JSON 数组 |
| `upload_tickets` | 上传票据 | 结构已就绪，接口尚未开放 |
| `settings` | 站点设置 | `key` 唯一，值为 JSON |
| `schema_version` | 迁移记录 | 版本号 + 名称 |

迁移位于 `server/sapic/migrations/__init__.py` 的 `MIGRATIONS`：`v001 initial`、`v002 album_ownership`、
`v003 image_tags`、`v004 image_visibility_without_shared`、`v005 plaza`、`v006 image_source_url`、
`v007 storage_scope_system`。
新增结构变更必须追加幂等迁移，不要直接改线上表。

## 6. 存储与副本

- 驱动 = `hooks/` 下的模块（`up2local` / `up2github` / `up2gitee` / `up2qiniu` / `up2upyun`），
  必须实现 `upimg_save(filename, stream, upload_path, backend)` 与 `upimg_delete(...)`。
- backend = 驱动的一份配置（bucket、目录、加速域名等），`config` 与钩子级默认配置在
  `libs/storage.driver_backend()` 合并，backend 行优先；`up2local` 未配置 `root` 时用 `STORAGE_DIR`。
- 上传是两级写入：`priority` 最小的启用后端**同步**写入（失败即上传失败），其余启用的后端随后由
  后台线程池（`libs/storage._REPLICA_POOL`）**异步**补副本，成功/失败记录在 `image_backends.state`
  + `last_error`；站点设置 `storage_replica` 可整体关闭。`is_primary` 标记同步写入的那一份。
- 读取（`/raw` 与公开图直链）按「后端 `priority` 升序、副本 id 升序」挑选 `state=ok` 且后端启用的副本，
  所以**优先级最高的后端既是写入目标，也是直链与读取的首选**。
- 存储 key 固定为 `{用户}/{年}/{月}/{日}/{ASCII 文件名}-{sha 片段}.{ext}`。
- **外链登记**（`images.source_url`）：只登记地址、不下载、不产生副本。公开图的 `src` 就是源站地址，
  私有图由 `/raw/<sha>` 转发；删除记录只删元数据，不触碰源站。
- **后端归属（scope）**：`system` 行是管理员维护的默认存储，可按 `UserBackend` 授权/排序给用户；
  `user` 行是用户自定义存储（`owner_id` 即归属人），只有本人可用。`list_backends(user)` 把两类合并后按
  有效优先级排序（授权行用 `UserBackend.priority` 覆盖），别人的 `user` 行对当前用户不可见。
  用户自定义能力由站点设置 `allow_user_backends`（默认关）把关，关着时即使库里有 `user` 行也不参与上传；
  用户端的增删改查 API 与界面尚未实现，管理员后台只管理 `system` 行。
- **公开图**直接返回主副本直链（驱动给了 `src`）；**私有图**固定走 `/raw/<sha>`，远程副本流式转发不暴露源站。
- 后端行（`storage_backends`）由「启用的存储钩子」自动派生：启动时与每次 `list_backends()` 都会
  `sync_backends()`，为每个启用的 `catalog=upload` 钩子补一行。**存储驱动的凭据只配在后端行**
  （`config`，新增/修改时按 `config_schema.required` 校验，缺项报 400 且列表标「待配置」）；
  早期版本存在 `hooks_config` 里的值会在同步时搬进后端行，`driver_backend()` 仍保留「后端覆盖钩子默认值」
  的合并逻辑以兼容旧配置。管理接口 `GET/POST/PATCH/DELETE /api/v2/backends`（`views/backends.py`，
  仅管理员）负责改优先级、启停、单独配置与删除。
- 写入目标是「启用的后端里 `priority` 最小者」；读图按副本所在后端回退。因此仍有副本的后端不许
  禁用/删除（409），也不许把最后一个启用后端关掉；删掉某驱动的最后一行等价于停用该钩子，
  否则下次同步会把它建回来。

## 7. 权限模型（相册为维度）

- 每张图片必须属于一个相册：登录用户 → 自己的默认相册，匿名上传 → 系统相册（`owner_id` 为空）。
- 有效可见性 = 单图 `images.visibility` 优先，为空则跟随相册 `albums.visibility`。
- 共享用 `album_shares`：`read` 只能浏览，`write` 允许把图片上传进该相册（仍不能动别人的图片）；
  过期授权等同不存在，鉴权统一走 `libs/albums.share_for()`。
- 个人图库（`GET /api/v2/images`）只含自己的图片 + 共享给自己的相册，**不含他人公开图片**；
  公开曝光走广场（`plaza_enabled` 默认关闭），广场只是曝光渠道，不改变可见性判定。
- 只有 `status=1`（正常）的账号能登录、持有会话或使用 PAT；禁用/拒绝会自增 `session_version`。

## 8. 钩子体系（声明式 UI 插件）

钩子用数据描述自己的界面，核心只做清洗与执行，前端不认识任何插件名：

| 钩子函数 | 作用 |
| --- | --- |
| `hook_manifest()` | `{title, catalog, config_schema, actions, data_sources, slots}` |
| `slot_<name>(context, values)` | 渲染某插槽的节点树 |
| `action_<name>(payload, context, values)` | `{code, message, toast, refresh}` |
| `data_<name>(query, context)` | `{items, total}` |

- 节点词表见 `libs/ui.py`（唯一可信来源），未知类型/键、非法 `href`、未声明的 `action` 一律丢弃。
- `slots` 必须在白名单内；`admin.*` 插槽与 `scope: "admin"` 的动作、数据集接口只允许管理员。
- 内置钩子：`up2local`、`up2github`、`up2gitee`、`up2qiniu`、`up2upyun`、`pic2webp`（图片后处理）、
  `passport`（OIDC 统一登录）。启用状态与配置存在 `settings.hooks_state` / `hooks_config`，
  第三方模块名存 `hooks_imported`，扫描目录可用 `HOOK_PKG_STORAGE_DIR` 扩展。
- 钩子私有依赖放 `requirements/hooks.txt`，用 `try/except ImportError` 兜底提示，不进 `base.txt`。

## 9. 配置与站点设置

- **进程配置**（`basis/conf.py`）：类默认值 ← `server/.cfg` ← `sapic_*` 环境变量，启动时校验
  （`SECRET_KEY` 长度与生产非默认值、`MAX_UPLOAD`/`SESSION_TTL` 为正整数、`STORAGE_DIR` 为绝对路径）。
- **站点设置**（`libs/settings.py` 的 `DEFAULTS`，存 `settings` 表）：站点展示、上传白名单/大小/视频开关、
  注册与审核、`password_login`、默认相册可见性、`plaza_enabled`、SMTP、钩子状态等。后台
  `GET/PUT /api/v2/settings` 维护，前台通过 `GET /api/v2/site` 读取展示字段。
- 新增配置项必须同时接入「后台表单 + 实际生效点」，避免只存不用。

## 10. 前端结构（web/）

- Vue 3 + Vite + Element Plus（`unplugin-auto-import` / `unplugin-vue-components` 按需引入）、Pinia、vue-router（history 模式）。
- `api/client.js` 统一封装信封解析、CSRF、401 回调与错误归一；页面不直接 `fetch`。
- `layout/AppLayout.vue` 提供背景/导航/页脚；`layout/AdminLayout.vue` 是后台外壳（侧栏 + `router-view`），
  四个管理页挂在 `/admin` 父路由下切换；`components/hook/*` 按后端节点树递归渲染钩子 UI。
- 开发期通过 Vite 代理把 `/api` 与 `/raw/` 转发到 `127.0.0.1:9514`，保持同源以便 Cookie 会话生效。

## 11. 扩展点速查

| 需求 | 落点 |
| --- | --- |
| 新增 API | `views/xxx.py` 建蓝图 + `views/__init__.register_blueprints` 注册，业务写 `libs/` |
| 新增表/字段 | `models/` 加模型 + `migrations/MIGRATIONS` 追加幂等迁移 |
| 新增配置项 | `basis/conf.py`（进程级）或 `libs/settings.DEFAULTS`（站点级）+ 生效点 |
| 新增存储驱动 | `hooks/up2xxx.py` 实现 `upimg_save` / `upimg_delete`，启用钩子后自动出现后端行 |
| 新增后台界面块 | 钩子 `slot_admin_*` 返回节点树 |
| 新增后台动作 | 钩子 `action_<name>`，涉及路径/凭据的标 `scope: "admin"` |
| **用户自定义存储（预留口子）** | 数据层已就绪：`storage_backends` 写 `scope="user"` + `owner`；`list_backends()` 已按归属过滤并支持 `UserBackend.priority` 覆盖；开关是 `allow_user_backends`。新接口只需在 `views/` 加用户端 CRUD（创建时固定 `scope="user"`、`owner=当前用户`，配置走 `libs/storage.clean_backend_config` + 必填校验），前端复用 `BackendsView` 的字段渲染即可 |

## 12. 已知限制

- 多副本是**上传时一次性扇出**：主后端同步、其余异步，失败只标 `image_backends.state=failed`。
  历史图片不会自动回填到新加的后端，也没有 CRC/存在性对账与自动修复。
- 上传票据（Upload Ticket）接口仍在待实现列表；存储后端已可管理，但还没有「按用户分配后端」的 UI。
- 钩子目前是「声明即信任 + 词表清洗」，没有签名校验与插件市场。
- 删除账号（`libs/users.purge_user`）是硬删除，不可恢复；`README`/`Snapshot` 等文档仍残留 v1 内容。
