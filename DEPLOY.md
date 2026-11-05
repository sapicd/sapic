# sapic v2 部署文档

本文是 sapic v2 的部署与运维手册：本地开发、生产部署（venv + gunicorn + nginx）、配置项、
数据库、钩子与统一登录、升级与备份。架构细节见 [ARCH.md](./ARCH.md)。

## 1. 组成与前置条件

```
nginx ─┬─ /         → web/dist（Vue 3 SPA，静态文件 + SPA 回退）
       ├─ /api/v2   → gunicorn 127.0.0.1:9514（Flask）
       └─ /raw/     → gunicorn 127.0.0.1:9514（图片读取）
```

| 组件 | 要求 | 说明 |
| --- | --- | --- |
| Python | 3.10+ | 后端只跑在 `server/`，包 `sapic` 是本地包，**不要** `pip install` 它 |
| 依赖 | `requirements/prod.txt`（离线可用 `base.txt` + gunicorn/gevent） | 装在仓库根的 `.venv/` |
| Node.js | 18+，pnpm 8（`packageManager: pnpm@8.14.1`） | 只在构建前端时用到 |
| 数据库 | PostgreSQL / MySQL 5.7+ / SQLite | 多 worker、多实例建议 PostgreSQL 或 MySQL |
| Redis | 可选 | 当前只用于 `GET /api/v2/health` 探活，不配也能跑 |
| nginx | 任意版本 | 反代 + 静态站点，需要支持 `try_files` |

> 数据目录：默认 SQLite 文件与本地图片都存在 `server/data/`（`sapic.db`、`upload/`），
> 启动时自动创建。生产环境请把它放到持久盘并纳入备份。

## 2. 本地开发

```bash
git clone <repo> && cd sapic
make setup          # 后端 dev.txt（仓库根 .venv）+ 前端 pnpm install
make dev            # 后端 0.0.0.0:9514，sapic_env=dev，改代码自动重启
make web-dev        # 另开一个终端：前端 127.0.0.1:5173，/api 与 /raw/ 代理到 9514
make test           # 后端 pytest
```

常用辅助命令：

```bash
make config                       # 打印当前生效配置（含默认值合并结果）
make create-admin U=admin P='密码'  # 创建管理员
make upgrade                      # 手动兜底执行迁移（启动时其实已自动执行）
```

## 3. 生产部署

### 3.1 拉代码与依赖

```bash
cd /srv && git clone <repo> sapic && cd sapic
python3 -m venv .venv
./.venv/bin/python -m pip install -U pip
./.venv/bin/python -m pip install -r requirements/prod.txt
# 需要 OIDC / 云存储 / 图片转码等钩子时再装可选依赖：
./.venv/bin/python -m pip install -r requirements/hooks.txt
```

### 3.2 构建前端

```bash
cd web && pnpm install && pnpm run build       # 产物在 web/dist，交给 nginx
```

### 3.3 写配置

在 `server/.cfg`（不入库）里逐行写 `key=value`，键名与环境变量一致，**值所见即所得**（不要加引号）：

```ini
sapic_secretkey=换成足够长的随机串
sapic_db_url=postgresql://sapic:password@127.0.0.1:5432/sapic
sapic_redis_url=redis://127.0.0.1:6379/0
sapic_storagedir=/data/sapic/upload
sapic_proxyfix=1
sapic_loglevel=INFO
sapic_session_ttl=604800
```

> 生产模式下 `SECRET_KEY` 若仍是内置默认值，`load_config()` 会直接报错退出——这是刻意设计的保险。

### 3.4 初始化数据库与管理员

```bash
cd server
../.venv/bin/python -m flask sa upgrade                      # 建表/迁移（幂等）
../.venv/bin/python -m flask sa create-admin -u admin -p '密码'  # 可加 -e 邮箱
```

生产环境需要 `FLASK_APP=sapic`（Makefile 会自动导出）；手工执行时请自行设置：

```bash
cd /srv/sapic/server && FLASK_APP=sapic ../.venv/bin/python -m flask sa upgrade
```

### 3.5 启动后端

前台试跑（确认能起来再交给 systemd）：

```bash
cd /srv/sapic && make serve HOST=127.0.0.1 WORKERS=4
# 等价于：cd server && ../.venv/bin/python -m gunicorn "sapic:create_app()" -b 127.0.0.1:9514 -w 4 -k gevent
```

systemd 单元示例 `/etc/systemd/system/sapic.service`：

```ini
[Unit]
Description=sapic v2
After=network.target postgresql.service

[Service]
Type=simple
User=www-data
WorkingDirectory=/srv/sapic/server
Environment=FLASK_APP=sapic
Environment=sapic_env=production
# 也可以只把配置放 server/.cfg，这里不再透出密钥
ExecStart=/srv/sapic/.venv/bin/python -m gunicorn "sapic:create_app()" \
          -b 127.0.0.1:9514 -w 4 -k gevent --timeout 60 --access-logfile - --error-logfile -
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload && systemctl enable --now sapic && systemctl status sapic
```

### 3.6 nginx 站点

```nginx
server {
    listen 443 ssl http2;
    server_name img.example.com;
    charset utf-8;

    #: 必须 >= 后端 MAX_UPLOAD（sapic_maxupload，默认 20M）与站点设置 upload_max_size
    client_max_body_size 25m;

    root /srv/sapic/web/dist;
    index index.html;

    #: 构建产物带 hash，可以长缓存；index.html 必须不缓存，否则发版后拿到旧壳
    location /assets/ {
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
    location = /index.html {
        add_header Cache-Control "no-store";
    }

    #: SPA（vue-router history 模式）
    location / {
        try_files $uri $uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:9514;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
    }

    location /raw/ {
        proxy_pass http://127.0.0.1:9514;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;      #: 大图/视频流式输出
    }
}
```

关键点：

- `sapic_proxyfix=1`（或环境变量）必须开：Flask 侧据此信任 `X-Forwarded-Proto/Host`，否则
  `request.is_secure` 为假，登录 Cookie 不会带 `Secure`，回调地址也可能拼错。
- **前后端同源**：`/api`、`/raw/` 与静态资源必须在同一个域名/端口下，Cookie 会话才生效。
- 想用 CDN 或独立图片域名时，配 `sapic_external_base_url=https://cdn.example.com`，
  `/raw` 链接会带该前缀。

## 4. 配置项参考（`server/.cfg` 或 `sapic_*` 环境变量）

| 配置项 | 环境变量 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `ENV` | `sapic_env` | `production` | 设为 `dev` 才允许内置默认密钥、开 DEBUG |
| `DEBUG` | `sapic_debug` | `false` | 开发用，生产必须关 |
| `SECRET_KEY` | `sapic_secretkey` | 内置占位值 | Cookie 签名密钥，≥14 字节，生产必须替换 |
| `DATABASE_URL` | `sapic_db_url` | `sqlite:///server/data/sapic.db` | 支持 `postgresql://` / `mysql://` / `sqlite:///` |
| `REDIS_URL` | `sapic_redis_url` | 空 | 留空则不连 Redis |
| `MAX_UPLOAD` | `sapic_maxupload` | `20` | 单文件上限（MB），同时映射 `MAX_CONTENT_LENGTH` |
| `STORAGE_DIR` | `sapic_storagedir` | `server/data/upload` | 本地存储根目录，必须是绝对路径 |
| `EXTERNAL_BASE_URL` | `sapic_external_base_url` | 空 | 图片链接前缀（CDN/独立域名） |
| `PROXY_FIX` | `sapic_proxyfix` | `false` | 反代后必须开 |
| `LOG_LEVEL` | `sapic_loglevel` | `INFO` | `DEBUG/INFO/WARNING/ERROR/CRITICAL` |
| `SESSION_TTL` | `sapic_session_ttl` | `604800` | 登录态有效期（秒），≥60 |
| `HOOK_PKG_STORAGE_DIR` | `sapic_hookpkgstoragedir` | 空 | 第三方钩子包目录 |

站点级设置（站点名、上传白名单/大小、注册与审核、`password_login`、默认相册可见性、广场开关、
SMTP、钩子开关与配置）存在数据库 `settings` 表，进后台 `/admin/setting` 维护，不走环境变量。

## 5. 数据库

```bash
# PostgreSQL
sapic_db_url=postgresql://user:pass@127.0.0.1:5432/sapic
# MySQL（自动加 charset=utf8mb4）
sapic_db_url=mysql://user:pass@127.0.0.1:3306/sapic
# SQLite（默认）
sapic_db_url=sqlite:////data/sapic/sapic.db
```

- 迁移在应用启动时**自动执行**（多 worker 并发启动有锁冲突重试 + 迁移幂等，安全）；
  `flask sa upgrade` 只作运维兜底。
- MySQL 的 DDL 不支持事务，所以每个迁移都写成可重复执行；升级失败先看日志再手工重跑即可。
- SQLite 适合单机小流量；多 worker 写并发下容易 `database is locked`，生产建议 PostgreSQL/MySQL。

## 6. 首次使用与常用配置

1. 用管理员账号登录后台，`/admin/setting` 填站点名/背景/公告，按需打开或关闭注册、匿名上传、图片广场。
2. 上传白名单 `upload_allowed_ext`、单文件大小 `upload_max_size`、视频开关 `allow_video` 在后台「站点设置」，
   与进程级 `sapic_maxupload` 是**两层限制**，两边都要放开才能传大文件。
3. 邮件（注册验证、找回密码）在后台配置 SMTP；不配也能用，但相关功能不可用。
4. 统一登录（OIDC）：`/admin/hooks` 启用 `passport`，填 `issuer` / `client_id` / `client_secret`；
   在 Passport 侧登记回调地址 `https://img.example.com/api/v2/auth/oidc/passport/callback`。
   站内首次登录会用 provider 的稳定标识（uid）建号，昵称只作显示名。
   关闭 `password_login` 后只能走统一登录，建议先给管理员账号绑定 OIDC 再关。
5. 存储后端：`up2local` 默认启用并自动创建 `local` 后端（写到 `STORAGE_DIR`）。要用云存储：
   ① 先 `pip install -r requirements/hooks.txt` 装对应 SDK；② `/admin/hooks` 只负责启用该驱动
   （存储驱动的凭据不再在这里填）；③ 进 `/admin/backends` 编辑该后端，填写必填项（带 *，如 bucket /
   操作员 / 密码 / 加速域名），可用「检查」探测存储桶；④ 把它「上移」到第一位（或把优先级调到最小），
   之后新上传才会写到它。已有图片按副本所在后端读取，所以仍有副本的后端不允许禁用/删除。

## 7. 升级、备份与回滚

升级：

```bash
cd /srv/sapic && git pull
./.venv/bin/python -m pip install -r requirements/prod.txt
cd web && pnpm install && pnpm run build
systemctl restart sapic        # 启动时自动跑增量迁移
```

备份：

- 数据库：`pg_dump` / `mysqldump` / 直接拷 `sapic.db`（先停服务或 `sqlite3 .backup`）。
- 本地图片：`STORAGE_DIR` 整个目录。
- `server/.cfg`（密钥与 DSN）。

回滚：迁移幂等但不支持自动回退，回滚代码前先备份数据库；结构不兼容的版本需手工降级数据。

## 8. 观测

- 健康检查：`GET /api/v2/health` → `{"status": "ok|degraded", "version", "database", "redis"}`，
  数据库不通返回 503；Redis 未配置时为 `null`，不影响判定。
- 日志：默认输出到 stdout（systemd 下 `journalctl -u sapic -f`）；日志级别用 `sapic_loglevel` 调。
- 每个请求都会带 `X-Request-Id`（也可由上游传入），排查时用它串日志。

## 9. 常见问题

| 现象 | 原因与处理 |
| --- | --- |
| 启动报 `SECRET_KEY must be configured in production` | 没配 `sapic_secretkey`，或 `sapic_env` 被设成了 `dev` |
| 启动报 `STORAGE_DIR must be an absolute path` | 用相对路径了，改成绝对路径 |
| 登录成功但刷新就掉线 | 反代没配 `X-Forwarded-Proto` + `sapic_proxyfix=1`，Cookie 的 `Secure` 与站点协议不一致 |
| 上传 413 | nginx `client_max_body_size` 与 `sapic_maxupload`、后台 `upload_max_size` 三者取最小值 |
| 上传提示 `file type is not allowed` | 后台 `upload_allowed_ext` 白名单没放开该后缀 |
| 访问 `/raw/xxx` 404 | 图片被删除，或副本已不在对应后端（查 `image_backends.state`） |
| OIDC 回调 400 `invalid oidc state` | 回调域名/协议与发起时不一致（`sapic_proxyfix`、Passport 侧回调地址） |
| 前端刷新 404 | nginx 缺 `try_files $uri $uri/ /index.html` |
| 后台看不到钩子 | hooks 目录未被扫描（`HOOK_PKG_STORAGE_DIR`）或依赖未装，看日志里的 ImportError |
