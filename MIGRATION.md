# V1 → V2 功能迁移对比表

对照对象：`V1/src`（v1，Flask + Redis + 模板渲染）与 `server/sapic` + `web/src`（v2，API-only + Vue 3 + Peewee）。

状态图例：

| 标记 | 含义 |
| --- | --- |
| ✅ | 已完成（v2 等价或增强） |
| 🟡 | 部分完成（有能力但缺关键环节） |
| ❌ | 未实现（v2 缺失） |
| 🔵 | v2 新增（v1 没有） |
| ⛔ | 有意不做（已确认不迁移） |

统计（按下表 78 项）：✅ 42 项、🟡 5 项、❌ 13 项、🔵 13 项、⛔ 5 项。

## 1. 上传

| # | 能力 | V1 | V2 | 状态 |
| --- | --- | --- | --- | --- |
| 1 | 表单文件上传 | `POST /api/upload`，字段名可配（`picbed`）`V1/src/views/api.py:1282` | `POST /api/v2/upload`，字段 `file`，可配 `album_id`/`title`/`expire` `views/uploads.py:60` | ✅（字段名/路径变更） |
| 2 | 远程 URL 上传（服务端抓取） | `picbed=<url>` `api.py:1334` | `url` 表单字段 + `download_image()`（含私网地址拦截）`libs/images.py:319`；直连超时/解析失败时可按站点设置 `upload_fetch_proxy` 走代理重试 | ✅（v2 增强：抓取代理兜底） |
| 3 | base64 / Data URI 上传 | 支持 `api.py:1334-1351` | 仅 file/url | ❌ |
| 4 | 外链列表「入库」（不下载文件，`/api/load`） | 支持批量导入外链 `api.py:1850` | `POST /api/v2/images/import`（`images.source_url`，不产生副本；公开图直连源站、私有图经 `/raw` 转发），前端「导入」弹窗（标题「导入外链图片」）支持多行粘贴 `views/images.py:100` | ✅ |
| 5 | 拖拽上传 | layui 拖拽 `templates/public/index.html:189` | `el-upload drag` `web/src/views/UploadView.vue:357` | ✅ |
| 6 | 粘贴上传（图片文件 / 图片 URL） | 支持 `index.html:341` | `window paste` 事件，两种都支持 `UploadView.vue:90-130` | ✅ |
| 7 | 多文件批量上传 | 前端队列 ≤ `upload_number`（默认 10），后端逐个 | `site.uploadCountLimit` 限制队列，前端逐个请求 `UploadView.vue:365` | ✅（后端同样无语义） |
| 8 | 后缀白名单 / 大小限制 | `upload_exts` + `upload_size`，叠加进程 `MaxUpload` `utils/web.py:974` | `upload_allowed_ext` + 按类型的大小上限（`upload_image_max_size` 10M / `upload_video_max_size` 20M）+ 进程 `MAX_UPLOAD`（25M）`views/uploads.py:46` | ✅（v2 更细：图片/视频分开） |
| 9 | 视频上传开关 | `upload_video`（默认关） | `allow_video`（默认开） `libs/settings.py` | ✅（默认值不同） |
| 10 | 匿名上传 | `anonymous`，图片归属 `anonymous` 账号 `api.py:1306` | `allow_anonymous_upload`，归入「系统相册」`views/uploads.py:30` | ✅（模型更干净） |
| 11 | 上传后端分组（`upload_group`：标签→sender） | 支持按用户标签选/随机后端 `api.py:1423` | 无（只有自动创建的 `local` 后端） | ❌ |
| 12 | 每用户/每标签上传配额（`upload_limit`） | 支持 `label:数量`，负数禁传 `api.py:1456` | 无 | ❌ |
| 13 | 自定义路径/文件名规则（`upload_path_rule`/`upload_file_rule` + 用户可覆盖） | 支持 `api.py:1460` | 固定 `{用户}/{Y}/{m}/{d}/{文件名}-{sha}.{ext}` `libs/images.py:101` | ❌ |
| 14 | 覆盖上传（同 sha 重新上传） | `?Action=overrideUpload` `api.py:1238` | 无 | ❌ |
| 15 | 图片有效期 | `expire` 只给 Redis 元数据设 TTL，文件不清理 `api.py:1504` | `expire` 秒数 → `images.expire_at`；到期后 `/raw`、详情、列表、广场一律视为不存在；清理任务硬删副本与记录（`before_request` 节流 + `flask sa purge-expired`），站点可配默认值与上限 `libs/images.py:441` | ✅（v1 文件残留问题已解决） |
| 16 | 图片后处理（转 webp） | `pic2webp` 钩子（默认禁用） | `hooks/pic2webp.py` 已移植 | ✅ |

## 2. 图片浏览与管理

| # | 能力 | V1 | V2 | 状态 |
| --- | --- | --- | --- | --- |
| 17 | 我的图片列表 | 瀑布流 `/pictures` + 个人中心图片 tab `templates/public/pictures.html` | 列表 + 游标分页 + 相册/关键词/标签筛选 `views/images.py:37` | ✅（改列表式，筛选项更强） |
| 18 | 关键词搜索 | 无 | `filename`/`title` 模糊匹配 `views/images.py:49` | 🔵 |
| 19 | 标签筛选 | 无（`tags` 不存在） | `images.tags` + 精确匹配 `views/images.py:55` | 🔵 |
| 20 | 单张详情 | `/api/sha/<sha>` `api.py:1168` | `GET /api/v2/images/<sha>`（含副本信息、`can_edit`）`views/images.py:77` | ✅ |
| 21 | 单张删除（属主/管理员，含后端文件） | 支持并回调 `upimg_delete` `api.py:1180` | 支持，软删元数据 + 逐副本 `upimg_delete` `libs/images.py:589` | ✅ |
| 22 | 批量操作（删除 / 移动相册 / 可见性 / 广场） | 无 | 列表多选 + `POST /images/batch/delete`、`PATCH /images/batch`（`views/images.py:139`） | 🔵（v1 没有，v2 新增） |
| 23 | 修改标题/所属相册 | 改相册名 `api.py:1219` | `PATCH` 改 `title`/`album_id`/`visibility`/`tags`/`plaza` `views/images.py:105` | ✅（更强） |
| 24 | 复制分享文本（URL/HTML/rST/Markdown/文件名/相册） | 4 种模板 `templates/ref/upload_show.html` | `libs.images.share_templates`（键名与 v1 一致）+ 详情页「复制与分享」区块（6 项均带复制按钮，相对地址自动补全） | ✅ |
| 25 | 视频播放 | 详情页 `<video>` 播放 `my.html:600` | 详情页原生 `<video controls>` 播放；列表/广场/上传结果按 `is_video` 取首帧做封面并标「视频」`ImageDetailView.vue:169` | ✅ |
| 26 | 个人 RSS（`/feed`，最近 10 张） | 登录态 `/feed`，模板渲染最近 10 张（含私有图）`front.py:159` | 无（v2 已移除 `views/feed.py`、`libs/feed.py`、`feed_query` 与站点/用户开关） | ⛔（有意不做：匿名聚合出口会把「某用户有哪些图、何时上传」暴露给任何抓取方，而收益只是低频的站外订阅；需要分享就发单图直链） |
| 27 | 油猴脚本（v1 `/sapic.user.js`，抓页面图片上传） | 支持 `front.py:94` | `GET /api/v2/userscript.user.js` 动态生成 Tampermonkey 脚本（`libs/userscript.py`）：Alt（或 Ctrl）+点击图片把 `src` 交给 `POST /api/v2/upload` 的 `url` 字段（服务端抓取，免 CORS）；源码不嵌令牌，首次运行粘贴只含 `upload` 的 PAT；用户级开关 `userscript_enabled` 关掉即 404，安装地址支持 `?token=`。地址在 `/api/v2` 下，反代只需 `/api/` 一条规则（v1 的根路径地址已移除） | ✅（比 v1 更安全：不再把 LinkToken 写进脚本源码） |
| 28 | 图片广场（公开曝光） | 无 | `GET /api/v2/plaza`，显式发布 + 站点开关（默认关）`views/plaza.py` | 🔵 |
| 29 | 管理员看全站图片 | `front.my?is_mgr=1` 复用个人中心 `admin.html:37` | 管理员在 `GET /images` 直接可见全部 `libs/images.py:548` | ✅（无独立「全站图片」页） |

## 3. 相册

| # | 能力 | V1 | V2 | 状态 |
| --- | --- | --- | --- | --- |
| 30 | 相册作为实体（名称/描述/封面/时间） | 无，仅图片 hash 上的字符串字段 `api.py:1550` | `albums` 表 + CRUD/封面上传 `views/albums.py` | 🔵 |
| 31 | 相册可见性（public/private/shared） | 无 | 相册级 `visibility` + 单图覆盖 | 🔵 |
| 32 | 相册共享成员（read/write、有效期） | 无 | `album_shares` + 增删改与权限校验 `libs/albums.py` | 🔵 |
| 33 | 默认相册 / 系统相册（匿名图归属） | 无（`anonymous` 账号兜底） | `albums.is_default` + `owner_id=NULL` 系统相册 `libs/albums.py:21` | 🔵 |

## 4. 账号与认证

| # | 能力 | V1 | V2 | 状态 |
| --- | --- | --- | --- | --- |
| 34 | 本地注册（禁用词、密码强度） | `/api/register`，`forbidden_username` `api.py:256` | 同语义 `views/auth.py:126` | ✅ |
| 35 | 本地登录 / 记住我 | `dSid` Cookie，2h / 7d `api.py:168` | 签名 Cookie，固定 `SESSION_TTL`（默认 7d）`libs/auth.py` | ✅（无「不记住」短会话） |
| 36 | 注册审核（待审核/已拒绝） | `review=1` → `-1`，拒绝 `-2` + **拒绝理由** + 通知邮件 `api.py:589` | `register_review` → `-1`/`-2`；`users.status_reason`（迁移 v010）+ PATCH 传 `reason`，待审核→通过/拒绝时给已验证邮箱发审核结果邮件 `libs/users.notify_review` | ✅ |
| 37 | 邮箱验证 | JWT 激活链接 `api.py:1036` | 令牌制 `POST /auth/email/verify` + `/confirm` `views/auth.py:433` | ✅ |
| 38 | 找回密码 | 需已验证邮箱 `api.py:328` | 同语义 `views/auth.py:382` | ✅ |
| 39 | 第三方 OAuth 登录（GitHub/QQ/微博…） | 核心只留 `site_auth` 钩子契约，实际靠第三方钩子 `front.py:41` | `passport`（OIDC）为内置实现；Provider 契约固化在 `libs/ext.py`（`__catalog__="auth"` + `oidc_authorize_url`/`oidc_exchange`，可选 `identity_issuer`），第三方包声明即可接入 `/api/v2/auth/oidc/<模块名>`，说明见 `docs/extend/provider.md`；仍无 GitHub/QQ/微博直连 | 🟡（能力形式变更） |
| 40 | 第三方账号绑定/解绑 | 由第三方钩子自行实现 | `GET /auth/identities`、`DELETE /auth/identities/<name>`（解绑需密码）`views/auth.py:323` | ✅ |
| 41 | API Token | 单用户单 token，`Authorization: Token` `api.py:873` | 多枚 PAT，`Bearer sp_…`，`read/upload/write/admin` 四档 scope `libs/auth.py:30` | ✅（增强） |
| 42 | LinkToken 分权引用（origin/ip/endpoint/method + er/ir 规则 + 绑定相册） | 完整实现 `api.py:1576`、`hooks/token.py:116` | 无（用 PAT + 相册共享替代） | ❌ |
| 43 | LinkToken 调用统计报表 | 有 `api.py:1799` + `report` 图表 | 无 | ❌ |
| 44 | 用户标签（管理员行内编辑，用于上传分组/配额） | `PUT /api/user?Action=label` `api.py:680` | `users.labels` 字段存在，无接口/UI | ❌ |
| 45 | 头像 | 仅 `avatar` URL 字段，前端借上传接口回填 `my.html:143` | 服务端接收文件 + 前端裁剪 `POST /auth/avatar`、`AvatarCropper.vue` | ✅（增强） |
| 46 | 自助注销账号 | `?Action=deleteAccount`（有图则拒绝）`api.py:1056` | `DELETE /auth/account`（密码二次确认 + 名下无图片 + 管理员不可自删）`libs/users.self_delete`，前端「账号信息」危险操作区 | ✅ |
| 47 | 会话吊销 | 改密即失效（cookie 内嵌密码 hash） | `session_version` 自增，改密/禁用/拒绝均吊销 `libs/auth.py:60` | ✅ |
| 48 | CSRF 防护 | 无 | Cookie 会话写操作需 `X-CSRF-Token` `libs/auth.py` | 🔵 |
| 49 | 用户个人设置（`ucfg_*`：背景、缩放、默认相册、URL 规则、油猴、RSS） | 支持 `my.html:183` | `GET/PUT /api/v2/auth/settings`（`user_settings` 键值 + 白名单校验 `libs/user_settings.py`），设置页「个性化」：油猴脚本开关、PC/移动端背景图、背景透明度；默认相册由 `albums.is_default` 承担，缩放/URL 规则在 v2 无对应功能，RSS 已整体移除（#26） | ✅ |
| 50 | 留言 / 审核拒绝后「再次申请」 | Redis 消息 + 管理员查看 `api.py:1018` | 无 | ❌ |
| 51 | 站内消息推送 | `push_user_msg` `utils/web.py:849` | 无 | ❌ |

## 5. 管理后台

| # | 能力 | V1 | V2 | 状态 |
| --- | --- | --- | --- | --- |
| 52 | 站点设置表单 | 单页全量表单 `admin.html:643` | `/admin/setting`（展示+上传+注册+广场+SMTP）`views/settings.py` | ✅（字段为子集） |
| 53 | 富文本公告/关于（白名单过滤） | `bulletin` + `allowtags/allowstyles` `web.py:393` | `site_announcement` 纯文本（`el-alert` 渲染） | 🟡 |
| 54 | 钩子启停 / 重载 | 支持 `api.py:406` | `PATCH /hooks/<name>`、`POST /hooks/reload` `views/hooks.py:91` | ✅ |
| 55 | 钩子配置表单 | `intpl_*setting` 模板片段 `hooks/*.py` | `config_schema` 声明式渲染 + `PUT /hooks/config/<name>` | ✅（机制升级） |
| 56 | 第三方钩子引入 | 模块名 + `pip -t` 安装 / 删除 | `POST /hooks/import`、`DELETE /hooks/import/<module>?purge=1`、`HOOK_PKG_STORAGE_DIR` 加入 `sys.path`（默认 `data/hooks`，不做目录扫描以免执行依赖代码）`libs/hook_pkg.py` | ✅ |
| 57 | 官方钩子市场（GitHub 列表） | `/api/github?Action=thirdHooks` + 缓存 `api.py:747` | `GET /hooks/market`（6 小时缓存、`sapic_hookmarketurl` 可换镜像），合并本地 installed/loaded 状态 `views/hooks.py` | ✅ |
| 58 | 后台 pip 安装依赖 | `/api/pip/install` `api.py:709` | `POST /hooks/install`（admin + 包名/镜像校验 + 180s 超时，`pip install --target`）+ `GET /hooks/packages` | ✅ |
| 59 | 用户列表 / 审核 / 禁用 / 设管理员 / 删除 | `/api/user` 全套 `api.py:462` | `GET/PATCH/DELETE /users` `views/users.py` | ✅ |
| 60 | 用户标签编辑 | 支持 | 无 | ❌（同 #44） |
| 61 | 测试邮件 | `/api/test?Action=sendmail` `api.py:729` | 无 | ❌ |
| 62 | 版本更新检测 | `/api/github?Action=latestRelease` `api.py:845` | `GET /settings/version`（admin，`sapic_updatecheckurl` 可关/换镜像，24h 进程内缓存）+ 后台侧栏底部版本入口与「可更新」标签 `libs/release.py`、`layout/AdminLayout.vue` | ✅ |
| 63 | 后台页面组织 | 单页 4 tab | 顶部单一「后台管理」入口 + `AdminLayout` 侧栏，在 `/admin/setting`、`/admin/hooks`、`/admin/backends`、`/admin/users` 间切换（`/admin` 重定向到站点设置） | 🔵（结构升级） |

## 6. 钩子与存储

| # | 能力 | V1 | V2 | 状态 |
| --- | --- | --- | --- | --- |
| 64 | `up2local` | 写 `static/upload`，走 `/static` | 写 `STORAGE_DIR`，走 `/raw/<sha>` 或直链 `hooks/up2local.py` | ✅ |
| 65 | `up2qiniu` / `up2upyun` / `up2github` / `up2gitee` | 4 个驱动可用 | 4 个驱动已移植 `hooks/up2*.py` | 🟡（见 #66） |
| 66 | 存储后端实例管理（建/改/删 backend、优先级、启停） | 靠站点设置里的驱动字段，天然可用 | 启用存储钩子自动建后端行；`/api/v2/backends` + `/admin/backends` 可增删改、调优先级、按后端覆盖配置；`scope=system/user` + `allow_user_backends` 为用户自定义存储留好数据与解析口子（用户端 CRUD/UI 待做） | ✅ |
| 67 | 存储优先级 / 多副本 | 单后端 + `upload_includes`（多值时随机取一） | `priority` 排序 + `image_backends` 副本表 + 按优先级回退 | 🔵 |
| 68 | 多副本异步复制 | 无 | 上传同步写主后端，其余启用后端由线程池异步补副本（`image_backends.state` 记 ok/failed，站点设置 `storage_replica` 可关） | 🔵（v1 没有，v2 新增） |
| 69 | `sendmail` 钩子（本地 SMTP → Open → SendCloud 降级） | 有 `hooks/sendmail.py` | 不迁移：`libs/mail.py` 只发本地 SMTP | ⛔ |
| 70 | `token` 钩子（Authorization: Token / LinkToken） | 有 `hooks/token.py` | 不迁移：PAT + `Bearer` 取代 | ⛔ |
| 71 | 钩子自定义页面 `/extendpoint/<hook>/<route>` | 支持 `front.py:142` | 无（钩子只能返回 manifest/插槽/动作/数据集） | ❌ |
| 72 | 钩子自定义 API `/api/extendpoint` | 支持（无鉴权，v1 自承风险）`api.py:1537` | 无（改为声明式 action + scope 校验） | ⛔（有意收敛） |

## 7. 平台、运维与工程

| # | 能力 | V1 | V2 | 状态 |
| --- | --- | --- | --- | --- |
| 73 | 存储层 | Redis 为主存储 | Peewee + PostgreSQL/MySQL/SQLite；运行时**不依赖 Redis**（连健康检查都只看数据库），只有 v1 迁移工具要读它 | ✅ |
| 74 | **V1 数据迁移（Redis → 关系库）** | — | `tools/migrate_v1_to_v2.py`：Redis 账号/图片元数据 → `users`/`albums`/`images`/`image_backends`，保留原 sha，幂等 + `--dry-run`；本地文件走存储驱动重传，`src` 已在主后端域名下的对象**原地采纳**（`--v1-src-prefix` / `--refresh-external`），大小/类型/尺寸取自 v1 的 `senders`，真正丢失的才登记外链 | ✅ |
| 75 | v1 API 兼容层（PicGo/uPic/Typora/油猴沿用 `/api/upload`） | — | **已移除，不再提供**：客户端统一改配 `POST /api/v2/upload`（v2 信封，`data.image.src`），PicGo / uPic / Typora / ShareX / 右键菜单的逐项配置与脚本见 `docs/usage.md` | ⛔ |
| 76 | 命令行 | `flask sa create/clean/upgrade(1.6→1.8)` `utils/cli.py` | `flask sa upgrade`、`create-admin`；无 `clean`，无数据迁移命令 | 🟡 |
| 77 | CORS 与安全响应头 | 全局 `cors` + `X-Frame-Options`/`nosniff` `app.py:100` | 无 CORS（同源设计），无安全头；跨域浏览器上传不可用 | 🟡 |
| 78 | 部署产物与多语言 | `Dockerfile`、`docker-compose.yml`、`kube-sapic.yaml`；后端 i18n（`dfr` 翻译） | 部署产物已齐（多阶段 Dockerfile + compose + k8s 清单 + 重写 `build.yml`/`ci.yml`）；界面**固定中文**、不引入 `vue-i18n`（v1 的 `dfr` 翻译不迁移），Element Plus 用内置中文语言包；后端 `message` 固定英文，由前端 `web/src/api/messages.js` 映射成中文展示 | ✅（多语言有意不做） |

## 8. 优先补齐建议

按「影响现有用户」排序：

**P0 — 不补就无法上线替换 v1**

1. ~~**V1 数据迁移工具**（#74）~~：已完成，`tools/migrate_v1_to_v2.py`（幂等、`--dry-run`、保留 sha、
   文件走存储驱动重传、缺失文件登记为外链）。用法见 `DEPLOY.md` 7.1。
2. ~~**v1 客户端兼容或明确迁移指引**（#75）~~：选了「迁移指引」——不再提供 `/api/upload`
   兼容端点，客户端按 `docs/usage.md` 改配 `POST /api/v2/upload`（PAT + `file` 字段 +
   `data.image.src`），文档覆盖 PicGo / uPic / ShareX / uTools / Typora / 右键菜单 / 油猴。

> 存储后端管理（#66）已完成：启用存储钩子即自动建后端，`/admin/backends` 可调优先级与单独配置。

**P1 — 高频使用、v1 用户会立刻发现**

4. ~~用户个人设置（#49）~~：已完成（油猴开关 + 个人背景），默认相册由 `albums.is_default` 承担。
5. ~~复制分享文本（#24）~~：已完成，`share_templates` 输出 URL/HTML/Markdown/rST，详情页另有文件名与相册可复制。
6. ~~自助注销账号（#46）~~：已完成，`DELETE /auth/account`（密码确认 + 无图 + 管理员不可自删）。
7. ~~注册审核拒绝理由 + 通知邮件（#36）~~：已完成（`users.status_reason` + `notify_review`）；剩余用户标签编辑（#44/#60）。
8. 视频播放（#25）：前端按 `is_video` 渲染 `<video>`。

**P2 — 明确取舍后再定**

9. LinkToken（#42/#43）：若仍要服务第三方站点直传，需要重新设计（PAT + 相册共享尚不能限制 origin/ip/endpoint）。
10. 上传分组与配额（#11/#12）、自定义路径规则（#13）。（油猴脚本 #27 已完成；RSS #26 有意不做）
11. CORS/安全头（#77）、容器与 K8s 清单（#78）。

**已知不迁移**：`sendmail` 钩子（#69）、`token` 钩子（#70）、`/api/extendpoint`（#72）。
