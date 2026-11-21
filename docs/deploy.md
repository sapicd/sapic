# 部署与运维

本文是 sapic v2 的生产部署与运维手册：组成部分、生产部署（venv + gunicorn + systemd + nginx）、
容器与编排、数据库、升级与备份、观测。

只想尽快跑起来，走[快速开始](quickstart.md)；本地开发环境见[安装与部署](install.md)；
配置项与站点设置的含义见[配置](config.md)；出问题看[常见问题](faq.md)。

## 组成与前置条件

```text
nginx ─┬─ /         → web/dist (Vue 3 SPA, static files + SPA fallback)
       ├─ /api/v2   → gunicorn 127.0.0.1:9514（Flask）
       └─ /raw/     → gunicorn 127.0.0.1:9514 (image reads)
```

| 组件 | 要求 | 说明 |
| --- | --- | --- |
| Python | 3.10+ | 后端只跑在 `server/`，包 `sapic` 是本地包，**不要** `pip install` 它 |
| 依赖 | `server/requirements/prod.txt`（离线可用 `base.txt` + gunicorn/gevent） | 装在仓库根的 `.venv/` |
| Node.js | 23+，pnpm 8（`packageManager: pnpm@8.14.1`） | 只在构建前端时用到 |
| 数据库 | PostgreSQL / MySQL 5.7+ / SQLite | 多 worker、多实例建议 PostgreSQL 或 MySQL |
| nginx | 任意版本 | 反代 + 静态站点，需要支持 `try_files` |

```{note}
默认 SQLite 文件与本地图片都存在 `server/data/`（`sapic.db`、`upload/`），启动时自动创建。
生产环境请把它放到持久盘并纳入备份。
```

## 生产部署

### 拉代码与依赖

```bash
cd /srv && git clone <repo> sapic && cd sapic
python3 -m venv .venv
./.venv/bin/python -m pip install -U pip
./.venv/bin/python -m pip install -r server/requirements/prod.txt
```

内置钩子（OIDC / 云存储 / 图片转码）的 SDK 已随 `base.txt` 一起装好，不需要再额外安装。

### 构建前端

```bash
cd web && pnpm install && pnpm run build       # output in web/dist, served by nginx
```

### 写配置

在 `server/.cfg`（不入库）里逐行写 `key=value`，键名与环境变量一致，**值所见即所得**（不要加引号）：

```ini
sapic_db_url=postgresql://sapic:password@127.0.0.1:5432/sapic
sapic_storagedir=/data/sapic/upload
sapic_proxyfix=1
sapic_loglevel=INFO
sapic_session_ttl=604800
```

`sapic_secretkey` 是**可选**的：不写就用内置默认密钥。但它是公开串，公网多用户站点建议加一行
`sapic_secretkey=<openssl rand -hex 32>`，否则读过源码的人能伪造会话 Cookie。

全部配置项的默认值与含义见[配置](config.md)的进程级配置表；站点级设置（站点名、上传白名单与大小、
注册审核、SMTP、钩子开关等）存在数据库的 `settings` 表里，进后台 `/admin/setting` 维护。

### 初始化数据库与管理员

```bash
cd /srv/sapic/server

# create tables / run migrations (idempotent; also runs on startup)
FLASK_APP=sapic ../.venv/bin/python -m flask sa upgrade

# create an admin (add -e for an email)
FLASK_APP=sapic ../.venv/bin/python -m flask sa create-admin -u admin -p 'password'
```

`flask` 命令需要 `FLASK_APP=sapic`：Makefile 会自动导出，手工执行（含容器里）时请显式带上。

### 启动后端

前台试跑（确认能起来再交给 systemd）：

```bash
cd /srv/sapic/server
../.venv/bin/python -m gunicorn "sapic:create_app()" -b 127.0.0.1:9514 -w 4 -k gevent
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
# or keep config in server/.cfg so secrets stay out of the unit file
ExecStart=/srv/sapic/.venv/bin/python -m gunicorn "sapic:create_app()" \
          -b 127.0.0.1:9514 -w 4 -k gevent --timeout 60 --error-logfile -
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload && systemctl enable --now sapic && systemctl status sapic
```

### nginx 站点

```nginx
server {
    listen 443 ssl http2;
    server_name img.example.com;
    charset utf-8;

    #: must be >= backend MAX_UPLOAD (sapic_maxupload, 25M) and the site image/video limits
    client_max_body_size 25m;

    root /srv/sapic/web/dist;
    index index.html;

    #: hashed assets can be cached long; index.html must not be, or releases serve the old shell
    location /assets/ {
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
    location = /index.html {
        add_header Cache-Control "no-store";
    }

    #: SPA (vue-router history mode)
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
        proxy_buffering off;      #: stream large images / video
    }
}
```

关键点：

- `sapic_proxyfix=1`（或环境变量）必须开：Flask 侧据此信任 `X-Forwarded-Proto/Host`，否则
  `request.is_secure` 为假，登录 Cookie 不会带 `Secure`，回调地址也可能拼错。
- 上面的示例是 **nginx 自己终止 TLS**，所以 `X-Forwarded-Proto $scheme` 是对的。如果 nginx
  前面还有一层 Traefik / WAF / 云负载均衡负责 TLS，`$scheme` 恒为 `http`，必须改成透传，
  否则会把外层的 `https` 覆盖掉（容器镜像里的 `docker/nginx.conf` 已用 `map` 做兜底）：

  ```nginx
  map $http_x_forwarded_proto $fwd_proto {
      default $http_x_forwarded_proto;
      ""      $scheme;   #: fall back to our own scheme without an outer layer
  }
  # use it inside each location
  proxy_set_header X-Forwarded-Proto $fwd_proto;
  ```

- **前后端同源**：`/api`、`/raw/` 与静态资源必须在同一个域名/端口下，Cookie 会话才生效。
- 想用 CDN 或独立图片域名时，配 `sapic_external_base_url=https://cdn.example.com`，
  `/raw` 链接会带该前缀。
- **上传上限是三层取最小值**：nginx 的 `client_max_body_size`、进程级 `sapic_maxupload`
  （映射 `MAX_CONTENT_LENGTH`）、站点设置里按媒体类型的单文件上限
  （`upload_image_max_size` / `upload_video_max_size`）。multipart 有额外开销，进程级上限要比
  站点上限略大。
- **防盗链**：用户可在「个性化」里为自己的公开图开启 Referer 校验，拦截发生在 `/raw/`，
  nginx 只要原样转发 `Referer`（默认就转发），不要清空它。图片走存储直链（存储后端配了加速域名、
  或图片是外链登记）时 sapic 不在链路上，需要在 CDN/静态服务器侧另外配置：

  ```nginx
  location /upload/ {
      #: keep this list in sync with the allowed referrer domains in user settings
      valid_referers none blocked server_names *.example.com;
      if ($invalid_referer) { return 403; }
  }
  ```

  阿里云 OSS / 腾讯云 COS 在控制台「防盗链」里配同一份白名单，并显式选择是否允许空 Referer。

### 容器与编排

镜像内已经包含 gunicorn + nginx（nginx 托管 `web/dist`，只把 `/api`、`/raw` 两条前缀反代给后端；
油猴脚本在 `/api/v2/userscript.user.js` 下，因此不需要单独开 location），默认监听 80 端口，
不需要再单独部署前端。容器内监听端口默认 `80`，可用 `SAPIC_HTTP_PORT` 改：`docker/nginx.conf`
是带端口占位符的模板，由 entrypoint 渲染到 `/etc/nginx/conf.d/default.conf`，健康检查也会跟着走
同一个端口。`docker-compose.yml` 只把宿主的 `SAPIC_PORT`（默认 `80`）映射到容器 `80`。

容器里的 nginx **默认不记访问日志**（`access_log off;`，同样由 entrypoint 渲染），日志只留应用那份；
需要访问记录时加 `-e SAPIC_NGINX_ACCESS_LOG=1`，访客请求会经 `/var/log/nginx/access.log`
（镜像里软链到 stdout）出现在 `docker logs` 里。

```bash
docker build -t sapic:local .
docker run -d --name sapic -p 80:80 \
    -e sapic_db_url="sqlite:////app/server/data/sapic.db" \
    -e sapic_external_base_url="https://sapic.example.com" \
    -v sapic-data:/app/server/data \
    sapic:local
```

公网多用户建议再加一行 `-e sapic_secretkey="$(openssl rand -hex 32)"`。

`docker compose up -d` 就是上面那个单容器 + SQLite 的形态：

```bash
SAPIC_BASE_URL='https://sapic.example.com' docker compose up -d
# to replace the built-in secret, prefix the command: SAPIC_SECRET_KEY="$(openssl rand -hex 32)"
```

要 PostgreSQL（多进程/多副本）时在 compose 的 `environment` 里加一行，compose 里不带数据库服务：

```yaml
      sapic_db_url: "postgresql://user:pass@db-host:5432/sapic"
```

`docker-compose.yml` 用 SQLite（库文件在 `sapic-data` 卷里）并把 worker 限成 1，配置全部走环境变量
（只列必需项，其余用默认值）；`kube-sapic.yaml` 只有 Deployment + Service 两个对象：单副本，
SQLite 落在节点本地目录（`hostPath: /data/sapic`），配置全部写在 Pod 的 `env` 里，不需要
Secret/ConfigMap/PVC/Ingress。命名空间由 `kubectl -n` 指定（对象里不写死），使用前替换镜像 tag、
hostPath 路径与 env 里的密钥/域名；没有 Ingress，Service 是 NodePort，外层 HTTPS 反代指向
`<节点IP>:<nodePort>`。多节点集群必须把 Pod 固定到同一节点，否则换节点就是空库。
两份清单都只列必需配置，其它项按需要补环境变量，清单见[配置](config.md)。

要点：

- **唯一必须挂载的路径**是 `/app/server/data`：SQLite 数据库、上传文件（`upload/`）与后台安装的
  第三方钩子包（`hooks/`）都在这里；不挂卷等于每次重建容器丢数据。
- 容器内 `sapic_proxyfix=true` 必须开启（compose 与 k8s 已配），否则日志与限流拿到的是 127.0.0.1。
- 健康检查统一用 `GET /api/v2/health`：数据库不通返回 503。
- 上传上限有三层，改大小时一起改：nginx `client_max_body_size`（容器内 32m）、
  `sapic_maxupload`（25）、后台 `upload_image_max_size` / `upload_video_max_size`。
- 本地磁盘存储只能单副本（`Recreate` 策略）；要多副本必须换成对象存储类钩子并给
  `/app/server/data` 配 RWX 卷。
- 外层 HTTPS 交给宿主机反代或集群外的网关（`kube-sapic.yaml` 只开 NodePort，没有 Ingress），
  并把 `sapic_external_base_url` 设成对外地址，否则图片直链与审核邮件里的登录链接会是内网地址。
  反代/Ingress 侧的请求体上限要 ≥ 32m，改成 Ingress 时记得加
  `nginx.ingress.kubernetes.io/proxy-body-size`。
- 前面再套一层 Traefik / WAF 时不用改配置：容器内 nginx 用 `map` **透传**上游的
  `X-Forwarded-Proto`，不会再把 `https` 覆盖成 `http`（OIDC 回调地址与会话 Cookie 的 `Secure`
  标志都依赖这个值）。前提是外层只**追加/转发**该头而不改写它；若 WAF 必须改写，用
  `sapic_external_base_url` 兜住链接生成，并单独核对 OIDC 回调。
- WAF 常见坑：`/api/v2/health` 要放行（否则探针被拦会反复重启）、`/raw/*` 关掉响应体检测
  （二进制图片会拖慢甚至误杀）、`/api/v2/hooks/*` 放宽超时（后台装钩子会跑 pip 几十秒）、
  请求体上限不小于 32m（取值链是 WAF ≥ nginx 32m > `sapic_maxupload` 25M > 站点单文件上限）。
- 升级：拉新镜像重启即可，启动时自动执行数据库迁移（迁移幂等，多 worker 并发有重试保护）。

## 数据库

```bash
# PostgreSQL
sapic_db_url=postgresql://user:pass@127.0.0.1:5432/sapic
# MySQL (charset=utf8mb4 is added automatically)
sapic_db_url=mysql://user:pass@127.0.0.1:3306/sapic
# SQLite (default)
sapic_db_url=sqlite:////data/sapic/sapic.db
```

- 迁移在应用启动时**自动执行**（多 worker 并发启动有锁冲突重试 + 迁移幂等，安全）；
  `flask sa upgrade` 只作运维兜底。
- MySQL 的 DDL 不支持事务，所以每个迁移都写成可重复执行；升级失败先看日志再手工重跑即可。
- SQLite 适合单机小流量；多 worker 写并发下容易 `database is locked`，生产建议 PostgreSQL/MySQL。

## 首次使用

1. 用管理员账号登录后台，`/admin/setting` 填站点名/背景/公告，按需打开或关闭注册、匿名上传、图片广场。
2. 上传白名单 `upload_allowed_ext`、图片大小 `upload_image_max_size`（默认 10M）、
   视频大小 `upload_video_max_size`（默认 20M）、视频开关 `allow_video` 在后台「站点设置」，
   与进程级 `sapic_maxupload`（默认 25M，整个请求）是**两层限制**，两边都要放开才能传大文件。
3. 图片有效期：`image_expire_default_days`（未指定时的默认寿命）与 `image_expire_max_days`
   （单图上限）在后台「站点设置 → 上传」配置，单位天，`0` 表示永久 / 不限制；设了上限后不再允许
   永久图片。到期图片会在请求期被节流清理（每进程最多每 5 分钟一批），想更准时可加 cron：
   `flask sa purge-expired`（应用目录下、用部署用的 Python 执行）。
4. 邮件（注册验证、找回密码）在后台配置 SMTP，或启用 `sendcloud` 等 `mail` 类钩子并填好 API 凭据
   （配置完整时优先于 SMTP）；不配也能用，但相关功能不可用。
   端口决定传输方式：465/994 走隐式 SSL（不勾 STARTTLS），587 勾 STARTTLS，25 一般都不用。
   阿里/腾讯企业邮箱用 465 + 授权码（不是登录密码）。
5. 统一登录（OIDC）：`/admin/hooks` 启用 `passport`，填 `issuer` / `client_id` / `client_secret`；
   在 Passport 侧登记回调地址 `https://img.example.com/api/v2/auth/oidc/passport/callback`。
   站内首次登录会用 provider 的稳定标识（uid）建号，昵称只作显示名。
   关闭 `password_login` 后只能走统一登录，建议先给管理员账号绑定 OIDC 再关。
6. 存储后端：`up2local` 默认启用并自动创建 `local` 后端（写到 `STORAGE_DIR`）。要用云存储：
   ① 对应 SDK 已随 `base.txt` 安装，无需额外操作（第三方钩子才要自己装依赖）；
   ② `/admin/hooks` 只负责启用该驱动（存储驱动的凭据不再在这里填）；
   ③ 进 `/admin/backends` 编辑该后端，填写必填项（带 *，如 bucket / 操作员 / 密码 / 加速域名），
   可用「检查」探测存储桶；④ 把它「上移」到第一位（或把优先级调到最小），之后新上传才会写到它。
   已有图片按副本所在后端读取，所以仍有副本的后端不允许禁用/删除。

各配置项的完整清单见[配置](config.md)。

## 升级、备份与回滚

升级：

```bash
cd /srv/sapic && git pull
./.venv/bin/python -m pip install -r server/requirements/prod.txt
cd web && pnpm install && pnpm run build
systemctl restart sapic        # incremental migrations run at startup
```

备份：

- 数据库：`pg_dump` / `mysqldump` / 直接拷 `sapic.db`（先停服务或 `sqlite3 .backup`）。
- 本地图片：`STORAGE_DIR` 整个目录。
- `server/.cfg`（密钥与 DSN）。

回滚：迁移幂等但不支持自动回退，回滚代码前先备份数据库；结构不兼容的版本需手工降级数据。

## 从 v1 升级

数据迁移（Redis → 关系库、文件走存储驱动重传、保留原 `sha`）是独立的一次性操作，完整参数、
云存储采纳规则与客户端改配置都在[从 v1 迁移数据](migrate-v1.md)。

这里只强调顺序：**先迁数据、再切流量**，迁移期间停掉 v1 的写入。

## 观测

- 健康检查：`GET /api/v2/health` → `{"status": "ok|degraded", "version", "database"}`，
  数据库不通返回 503。
- 日志：只记**应用日志**，同时写文件与 stdout（systemd 下 `journalctl -u sapic -f`）。
  文件在 `sapic_log_dir`（默认 `<server>/data/log`）下的 `sys.log`，按天轮转、保留 10 天
  （归档名如 `sys.log.20261121`）；多 worker 下各进程各自轮转，量大时交给 logrotate。
  行格式与其它服务一致，方便统一采集：`[ INFO ] 2026-11-21 09:09:41 images.py:735 消息`；
  请求内的记录在消息前多一个 `rid=<X-Request-Id>`，可与前端报错里的请求 ID 对上。
  **不记访问日志**：gunicorn 没开，容器里的 nginx 也默认 `access_log off;`，要记录下来就设
  `SAPIC_NGINX_ACCESS_LOG=1`（见「容器与编排」）。日志级别用 `sapic_loglevel` 调；
  把 `sapic_log_dir` 置空则只保留 stdout/stderr。
- 每个请求都会带 `X-Request-Id`（也可由上游传入），排查时用它串日志。

### 后台任务（到期清理与审核扫描）

两类后台任务由进程内 APScheduler 驱动，随服务启动，**不需要 cron**：

| 任务 | 默认间隔 | 作用 |
| --- | --- | --- |
| 过期清理 | 600s（`sapic_scheduler_purge_interval`） | 删除到期图片的对象与元数据 |
| 审核扫描 | 300s（`sapic_scheduler_review_interval`） | 调 `moderator` 钩子判定未审的图；无此钩子时直接跳过 |

- **多 worker 选主**：每个 worker 启动时抢 `server/data/scheduler.lock` 的文件锁（`flock`），
  只有抢到的进程跑调度，其余跳过，所以 `gunicorn -w 4` 不会跑四份。
- **多副本**：各 Pod 有独立数据卷时锁不共享，会各自跑一份。调度任务本身幂等
  （清理按行、审核按行原子抢占），重复执行只是浪费；要严格单点就在 web 端设
  `sapic_scheduler=0`，另起一个 `flask sa scheduler` 的独立 Deployment / systemd 服务。
- **独立进程跑**（web 让位）：

  ```bash
  # web 侧：sapic_scheduler=0
  cd /srv/sapic/server && ../.venv/bin/flask sa scheduler   # 前台常驻，日志进 sys.log
  ```
- 一次性执行（k8s CronJob 等）：

  ```bash
  cd /srv/sapic/server && ../.venv/bin/flask sa scheduler --once
  ```
- **后台可观测**：管理员在「后台管理 → 定时任务」看当前调度者、两个任务的间隔/下次运行/上次结果，
  也可以「立即执行」一次（同步执行、批量很小，不会等太久）。多 worker 下这一页显示的是
  **处理该请求的进程**：落在待命进程时会标「其他进程调度中」，手动执行仍然有效。
- 审核命中只把图片**隐藏**（`review_state=block`），记录与文件都还在；管理员在
  `GET /api/v2/review?state=block` 里复核，`POST /api/v2/review/<sha>` 用
  `approve` 恢复或 `purge` 物理删除。
- 钩子需要能拿到图片地址时，先配 `sapic_external_base_url`（扫描把 `external_base_url + /raw/<sha>`
  交给钩子）。契约见[内容审核](extend/moderator.md)。

## 常见问题

启动失败、登录掉线、上传 413、`/raw` 404、钩子装不上等症状统一归到[常见问题](faq.md)，
本页只讲「怎么装起来」。
