# sapic server (v2)

sapic v2 后端，API-only（前端由独立的 Vue 应用提供）。

## 运行要求

- Python 3.10+
- PostgreSQL（推荐）或 MySQL 8
- Redis（会话、限流、异步任务）

## 依赖安装

本包是**纯本地包**，不发布 PyPI、也不 `pip install` 本包；依赖由本目录下的 `requirements/` 管理。
在**仓库根**执行：

```bash
make setup            # 开发 + 测试依赖 (server/requirements/dev.txt) + 前端依赖
# 仅后端（在 server/ 下）：python -m pip install -r requirements/dev.txt
```

## 配置

配置读取顺序：配置类默认值（`basis/conf.py`）→ `server/.cfg`（`key=value`）→ 环境变量（`sapic_` 前缀），
读取后逐项校验。`sapic_env=dev`（或 `FLASK_ENV=development`）切换到 `DevConfig`（开启调试与 DEBUG 日志）。

| 配置项 | 说明 | 默认值 |
| --- | --- | --- |
| `sapic_env` | 运行环境，`dev`/`development` 为开发模式 | `production` |
| `sapic_db_url` | 数据库 DSN，如 `postgresql://user:pass@host:5432/sapic`、`mysql://...`、`sqlite:///tmp/sapic.db` | `sqlite:///<server>/data/sapic.db` |
| `sapic_redis_url` | Redis DSN，如 `redis://:pass@host:6379/0` | 空（可选） |
| `sapic_secretkey` | Web 应用密钥，**生产必须显式配置**（缺省时启动失败；`sapic_env=dev` 才允许回落内置值） | 内置串 |
| `sapic_maxupload` | 整个上传请求的上限（MB，映射 `MAX_CONTENT_LENGTH`），要大于站点里图片/视频的单文件上限 | `25` |
| `sapic_storagedir` | 本地存储目录 | `data/upload` |
| `sapic_external_base_url` | 对外访问根地址，用于拼接图片外链 | 空（相对地址） |
| `sapic_proxyfix` | 是否信任代理标头 | 关闭 |

## 数据库初始化

建表与增量迁移（含 ALTER）在应用启动时自动执行，无需手动操作；多 worker 并发启动
由重试 + 幂等保证。需要手动兜底时才执行：

```bash
cd server
export FLASK_APP=sapic
flask sa upgrade          # 建表 / 增量迁移（启动时已自动执行）
flask sa create-admin -u admin -p 123456
flask sa purge-expired    # 手动清理到期图片（请求期也会节流兜底清理）
```

## 启动

```bash
cd server
flask run --host 0.0.0.0 --port 9514
```

生产环境使用 gunicorn：

```bash
gunicorn "sapic:create_app()" -b 0.0.0.0:9514 -w 4 -k gevent
```

## API 概览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/v2/health` | 健康检查（DB / Redis） |
| POST | `/api/v2/auth/register` | 注册 |
| POST | `/api/v2/auth/login` | 登录（Cookie 会话，返回 CSRF） |
| POST | `/api/v2/auth/logout` | 登出 |
| GET | `/api/v2/auth/session` | 当前会话 |
| POST | `/api/v2/auth/password/forgot` | 发送重置令牌（10 分钟） |
| POST | `/api/v2/auth/password/reset` | 使用令牌重置密码 |
| PUT | `/api/v2/auth/password` | 修改密码（吊销其它会话） |
| GET/POST | `/api/v2/auth/tokens` | 列出 / 创建 PAT（`scopes` 支持 `read`/`upload`/`write`/`admin`，缺省为前三项） |
| DELETE | `/api/v2/auth/tokens/<id>` | 撤销 PAT |
| GET | `/api/v2/auth/oidc/<name>` | 发起统一登录（`?bind=1` 则绑定当前账号） |
| GET | `/api/v2/auth/oidc/<name>/callback` | 统一登录回调 |
| GET | `/api/v2/auth/identities` | 可绑定的登录方式与绑定状态 |
| DELETE | `/api/v2/auth/identities/<name>` | 解除绑定（需当前密码） |
| POST | `/api/v2/uploads` | 上传（multipart，字段 `file` 或 `url`，可选 `expire` 有效期秒数与 `album_id`） |
| GET | `/api/v2/images` | 图片列表（游标分页，权限过滤） |
| POST | `/api/v2/images/import` | 批量登记外链（不下载文件，`items` 为链接数组，可指定 `album_id`） |
| POST | `/api/v2/images/batch/delete` | 批量删除（`shas`，≤100） |
| PATCH | `/api/v2/images/batch` | 批量修改：`album_id` / `visibility` / `plaza` / `tags` |
| GET/PATCH/DELETE | `/api/v2/images/<sha>` | 详情 / 修改（含 `expire_at` 有效期）/ 删除 |
| GET/POST | `/api/v2/albums` | 相册列表 / 创建 |
| PATCH/DELETE | `/api/v2/albums/<id>` | 修改 / 删除（非空拒绝） |
| GET/POST | `/api/v2/backends` | 存储后端列表 / 新增（仅管理员） |
| PATCH/DELETE | `/api/v2/backends/<id>` | 改优先级、启停、按后端覆盖配置 / 删除（仍有副本则 409） |
| GET | `/raw/<sha>` | 图片读取（公开图 302 到后端直链；私有图鉴权后输出，支持 Range） |
| GET | `/api/v2/userscript.user.js` | 油猴脚本（Tampermonkey/Violentmonkey），需登录；受个人设置 `userscript_enabled` 控制，可用 `?token=`（`upload` scope）安装 |
| GET/PUT | `/api/v2/auth/settings` | 个人偏好：`userscript_enabled` / `bg_image` / `bg_image_mobile` / `bg_opacity` |

认证方式：Cookie 会话（写操作需要 `X-CSRF-Token`）或 `Authorization: Bearer <PAT>`。

统一登录（OIDC，由 `passport` 钩子提供）：

- 登录顺序：身份已绑定 → 直接登录；未绑定但 provider 已验证的邮箱与本地已验证账号一致 → 自动关联；否则按 provider 信息自动建号（新用户的主要入口，同时创建默认相册）。
- 新账号的本地用户名取 provider 的稳定标识（Passport 即 `sub`／uid，22 位小写），昵称仅写入 `nickname` 作显示名——昵称可改、可重复，不适合当账号名。
- 邮箱关联始终启用，且要求**provider 与本地账号的邮箱都验证过**：provider 缺 `email_verified` 字段按已验证处理、显式 `false` 不关联；本地邮箱需先通过验证流程，避免「抢填他人邮箱」的账号被接管。
- 邮箱验证：注册时自动寄出令牌，也可在「账号设置」重新发送（`POST /api/v2/auth/email/verify`），提交令牌到 `POST /api/v2/auth/email/confirm` 后置为已验证；修改邮箱会重置为未验证，旧令牌随之失效。找回密码（`/auth/password/forgot`）同样只对已验证邮箱签发令牌。
- 已登录用户可在「账号设置 → 统一登录」绑定/解绑；解绑需输入当前密码，避免 OIDC 专用账号（随机密码）把自己锁在门外。
- 站点设置 `password_login` 关闭后，密码登录与本地注册一并停用，只能通过统一登录进入。

图片列表（`GET /api/v2/images`，需登录）是个人图库：只返回自己的图片和共享给自己的相册，别人的公开图片不会出现（公开曝光走广场，需显式发布）；匿名请求返回 401。公开图片仍可按 `src` / `/raw/<sha>` 直接访问。

图片地址（`src`）策略：

- **公开图片**：返回优先级最高的存储后端直链，流量不经过 sapic。直链来自钩子 `upimg_save` 返回的 `src`：各后端的「加速域名」配置（`domain`）优先；本地存储没配则回落代理，GitHub/Gitee 没配则用 `download_url`（GitHub 再兜底 jsDelivr）。
- **私有图片**（私有相册或单图覆盖 `visibility=private`）：始终返回 `/raw/<sha>`，由 sapic 鉴权后输出；远程副本会被流式转发，不会暴露源站地址。
- **没有直链的后端**（如未配置 `domain` 的本地存储）：回落到 `/raw/<sha>`，本地副本流式输出并支持 Range。
- **缓存**：公开图 `Cache-Control: public, max-age=31536000, immutable`；私有图 `private, max-age=31536000, immutable`（只允许浏览器缓存，共享缓存不缓存）。

存储 key 形如 `{用户}/{年}/{月}/{日}/{ASCII 文件名}-{sha 片段}.{ext}`：后缀保证同名文件不会互相覆盖。文件名统一经 `secure_filename` 清洗（中文等非 ASCII 字符被丢弃），主体被整段清空时用 `{yyyyMMddHHmmss}{6 位随机}` 兜底，后缀始终保留；删除按 `ImageBackend.object_key` 执行。

媒体元数据：上传时只从文件头读取 `width`/`height`（不引入图像库、不解码像素），并在落盘前**剥离 EXIF/XMP**（JPEG APP1、PNG `eXIf`/XMP 文本块、WebP `EXIF`/`XMP ` 块），拍摄时间、相机与 GPS 不会出现在存储对象里；GIF/BMP/ICO/SVG 与视频原样保存。

图片有效期：上传时 `expire` 传秒数（`0`/不传 = 按站点默认，默认永久），之后可用 `PATCH /images/<sha>` 的 `expire_at`（秒级时间戳，`null` 取消）调整。到期后图片立即按不存在处理（`/raw/<sha>`、详情、列表、广场均 404/消失），并在后台被**硬删除**（对象文件 + 副本 + 记录）。清理由请求期节流兜底（每个进程最多每 5 分钟一批），也可用 `flask sa purge-expired` 交给 cron。站点设置 `image_expire_default_days` 控制默认寿命、`image_expire_max_days` 控制上限（后者生效后不再允许永久图片）。

油猴脚本（`GET /api/v2/userscript.user.js`，需登录）：按用户生成 Tampermonkey/Violentmonkey 脚本，在任意网页 **Alt + 点击图片** 即可把它上传到本站。上传走 `POST /uploads` 的 `url` 字段（服务端抓取，绕过浏览器 CORS），脚本源码**不含任何令牌**：首次上传时弹窗要求粘贴一枚只勾选「上传图片」的 PAT，存在油猴存储里，可随时在脚本菜单里更换。脚本是否可安装由个人设置 `userscript_enabled` 决定（默认关），关掉后安装/更新地址立即 404；安装地址也接受 `?token=<PAT>`（`upload` scope），供无法携带 Cookie 的客户端使用。

图片广场（`GET /api/v2/plaza`，匿名可访问）：

- 广场是**曝光渠道**，不改变任何权限：`visibility` 仍然决定谁能看，只有有效可见性为 `public` 的图片会进入列表。
- 发布必须显式：相册级开关 `albums.plaza`，单图三态 `images.plaza`（`NULL` 跟随相册、`true` 强制发布、`false` 强制排除）。
- 站点设置 `plaza_enabled` **默认关闭**（个人图床不需要公开曝光渠道，公开 UGC 还会带来内容审核负担）；开启后 `GET /api/v2/plaza` 才可用，关闭时接口 404、前端所有广场入口随之隐藏。
- 迁移 `v005 plaza` 添加这两列，存量图片默认不上广场。

## 当前实现范围

- 已完成：应用工厂、Peewee 模型、迁移框架、健康检查、注册/登录/找回密码/PAT、上传与读取、相册权限、相册共享成员（增减成员与调整权限）、存储后端管理与优先级。
- 待实现：上传票据（Upload Ticket）、副本对账/自动回填、用户自定义存储后端的 API/UI
  （数据层见 `scope="user"` + 站点开关 `allow_user_backends`）、第三方插件安装持久化。

存储后端：启用的存储钩子（`catalog=upload`）在启动时与每次解析后端时自动补一行 `storage_backends`，
凭据来自「钩子配置」，可按后端覆盖。上传写入 `priority` 最小的启用后端；仍有副本的后端不能禁用/删除，
删掉某驱动的最后一行等同于停用该钩子（否则下次同步会重建）。

## 测试

```bash
cd server
python -m pytest -q
```

测试默认使用临时 SQLite 数据库；CI 建议增加 PostgreSQL / MySQL 双库矩阵。
