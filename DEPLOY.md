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
| 依赖 | `server/requirements/prod.txt`（离线可用 `base.txt` + gunicorn/gevent） | 装在仓库根的 `.venv/` |
| Node.js | 18+，pnpm 8（`packageManager: pnpm@8.14.1`） | 只在构建前端时用到 |
| 数据库 | PostgreSQL / MySQL 5.7+ / SQLite | 多 worker、多实例建议 PostgreSQL 或 MySQL |
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
./.venv/bin/python -m pip install -r server/requirements/prod.txt
```

内置钩子（OIDC / 云存储 / 图片转码）的 SDK 已随 `base.txt` 一起装好，不需要再额外安装。

### 3.2 构建前端

```bash
cd web && pnpm install && pnpm run build       # 产物在 web/dist，交给 nginx
```

### 3.3 写配置

在 `server/.cfg`（不入库）里逐行写 `key=value`，键名与环境变量一致，**值所见即所得**（不要加引号）：

```ini
sapic_secretkey=换成足够长的随机串
sapic_db_url=postgresql://sapic:password@127.0.0.1:5432/sapic
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

    #: 必须 >= 后端 MAX_UPLOAD（sapic_maxupload，默认 25M）与站点设置里的图片/视频上限
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
- 上面的示例是 **nginx 自己终止 TLS**，所以 `X-Forwarded-Proto $scheme` 是对的。如果 nginx
  前面还有一层 Traefik / WAF / 云负载均衡负责 TLS，`$scheme` 恒为 `http`，必须改成透传，
  否则会把外层的 `https` 覆盖掉（容器镜像里的 `docker/nginx.conf` 已用 `map` 做兜底）：

  ```nginx
  map $http_x_forwarded_proto $fwd_proto {
      default $http_x_forwarded_proto;
      ""      $scheme;   #: 没有外层时回落到自身协议
  }
  # 各 location 内改用它
  proxy_set_header X-Forwarded-Proto $fwd_proto;
  ```
- **前后端同源**：`/api`、`/raw/` 与静态资源必须在同一个域名/端口下，Cookie 会话才生效。
- 想用 CDN 或独立图片域名时，配 `sapic_external_base_url=https://cdn.example.com`，
  `/raw` 链接会带该前缀。
- **防盗链**：用户可在「个性化」里为自己的公开图开启 Referer 校验，拦截发生在 `/raw/`，
  nginx 只要原样转发 `Referer`（默认就转发），不要清空它。图片走存储直链（存储后端配了加速域名、
  或图片是外链登记）时 sapic 不在链路上，需要在 CDN/静态服务器侧另外配置：

  ```nginx
  location /upload/ {
      #: 名单要与用户设置里的「允许引用的域名」保持一致
      valid_referers none blocked server_names *.example.com;
      if ($invalid_referer) { return 403; }
  }
  ```

  阿里云 OSS / 腾讯云 COS 在控制台「防盗链」里配同一份白名单，并显式选择是否允许空 Referer。

### 3.7 容器部署（Docker / Compose / Kubernetes）

镜像内已经包含 gunicorn + nginx（nginx 托管 `web/dist`，只把 `/api`、`/raw` 两条前缀反代给后端；
油猴脚本在 `/api/v2/userscript.user.js` 下，因此不需要单独开 location），默认监听 80 端口，
不需要再单独部署前端。容器内监听端口默认 `80`，可用 `SAPIC_HTTP_PORT`
改：`docker/nginx.conf` 是带端口占位符的模板，由 entrypoint 渲染到
`/etc/nginx/conf.d/default.conf`，健康检查也会跟着走同一个端口。`docker-compose.yml`
只把宿主的 `SAPIC_PORT`（默认 `80`）映射到容器 `80`。

```bash
docker build -t sapic:local .
docker run -d --name sapic -p 80:80 \
    -e sapic_secretkey="$(openssl rand -hex 32)" \
    -e sapic_db_url="sqlite:////app/server/data/sapic.db" \
    -e sapic_external_base_url="https://sapic.example.com" \
    -v sapic-data:/app/server/data \
    sapic:local
```

`docker compose up -d` 就是上面那个单容器 + SQLite 的形态：

```bash
SAPIC_SECRET_KEY="$(openssl rand -hex 32)" SAPIC_BASE_URL='https://sapic.example.com' docker compose up -d
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
两份清单都只列必需配置，其它项按需要补环境变量，清单见下一节。

要点：

- **唯一必须挂载的路径**是 `/app/server/data`：SQLite 数据库、上传文件（`upload/`）与后台安装的第三方钩子包（`hooks/`）都在这里；不挂卷等于每次重建容器丢数据。
- 容器内 `sapic_proxyfix=true` 必须开启（compose 与 k8s 已配），否则日志与限流拿到的是 127.0.0.1。
- 健康检查统一用 `GET /api/v2/health`：数据库不通返回 503。
- 上传上限有三层，改大小时一起改：nginx `client_max_body_size`（容器内 32m）、`sapic_maxupload`（25）、后台 `upload_image_max_size` / `upload_video_max_size`。
- 本地磁盘存储只能单副本（`Recreate` 策略）；要多副本必须换成对象存储类钩子并给 `/app/server/data` 配 RWX 卷。
- 外层 HTTPS 交给宿主机反代或集群外的网关（`kube-sapic.yaml` 只开 NodePort，没有 Ingress），并把 `sapic_external_base_url` 设成对外地址，否则图片直链与审核邮件里的登录链接会是内网地址。反代/Ingress 侧的请求体上限要 ≥ 32m，改成 Ingress 时记得加 `nginx.ingress.kubernetes.io/proxy-body-size`。
- 前面再套一层 Traefik / WAF 时不用改配置：容器内 nginx 用 `map` **透传**上游的 `X-Forwarded-Proto`，不会再把 `https` 覆盖成 `http`（OIDC 回调地址与会话 Cookie 的 `Secure` 标志都依赖这个值）。前提是外层只**追加/转发**该头而不改写它；若 WAF 必须改写，用 `sapic_external_base_url` 兜住链接生成，并单独核对 OIDC 回调。
- WAF 常见坑：`/api/v2/health` 要放行（否则探针被拦会反复重启）、`/raw/*` 关掉响应体检测（二进制图片会拖慢甚至误杀）、`/api/v2/hooks/*` 放宽超时（后台装钩子会跑 pip 几十秒）、请求体上限不小于 32m（取值链是 WAF ≥ nginx 32m > `sapic_maxupload` 25M > 站点单文件上限）。
- 升级：拉新镜像重启即可，启动时自动执行数据库迁移（迁移幂等，多 worker 并发有重试保护）。

## 4. 配置项参考（`server/.cfg` 或 `sapic_*` 环境变量）

| 配置项 | 环境变量 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `ENV` | `sapic_env` | `production` | 设为 `dev` 才允许内置默认密钥、开 DEBUG |
| `DEBUG` | `sapic_debug` | `false` | 开发用，生产必须关 |
| `SECRET_KEY` | `sapic_secretkey` | 内置占位值 | Cookie 签名密钥，≥14 字节，生产必须替换 |
| `DATABASE_URL` | `sapic_db_url` | `sqlite:///server/data/sapic.db` | 支持 `postgresql://` / `mysql://` / `sqlite:///` |
| `MAX_UPLOAD` | `sapic_maxupload` | `25` | 整个请求的上限（MB），同时映射 `MAX_CONTENT_LENGTH`；要 ≥ 站点设置里的最大值并留出 multipart 余量 |
| `STORAGE_DIR` | `sapic_storagedir` | `server/data/upload` | 本地存储根目录，必须是绝对路径 |
| `EXTERNAL_BASE_URL` | `sapic_external_base_url` | 空 | 图片链接前缀（CDN/独立域名） |
| `PROXY_FIX` | `sapic_proxyfix` | `false` | 反代后必须开 |
| `LOG_LEVEL` | `sapic_loglevel` | `INFO` | `DEBUG/INFO/WARNING/ERROR/CRITICAL` |
| `SESSION_TTL` | `sapic_session_ttl` | `604800` | 登录态有效期（秒），≥60 |
| `HOOK_PKG_STORAGE_DIR` | `sapic_hookpkgstoragedir` | `server/data/hooks` | 第三方钩子包目录：`pip install --target` 的目标，并被加入 `sys.path`（**不作为扫描目录**，钩子靠模块名引入）；置空则关闭后台安装能力 |
| `HOOK_MARKET_URL` | `sapic_hookmarketurl` | 官方 GitHub 的 `list.json` | 钩子市场列表地址，可指向镜像 |
| `UPDATE_CHECK_URL` | `sapic_updatecheckurl` | 官方 GitHub 的 `releases/latest` | 后台版本更新检测的发布源；置空则关闭检测（纯内网部署用） |

站点级设置（站点名、上传白名单/大小、注册与审核、`password_login`、默认相册可见性、广场开关、
URL 抓取代理、SMTP、钩子开关与配置）存在数据库 `settings` 表，进后台 `/admin/setting` 维护，
不走环境变量。URL 抓取代理（`upload_fetch_proxy`）只在直连失败时生效，填集群内可达的
`http(s)://[user:pass@]host:port`；容器里 `127.0.0.1` 指的是容器自身。

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
2. 上传白名单 `upload_allowed_ext`、图片大小 `upload_image_max_size`（默认 10M）、
   视频大小 `upload_video_max_size`（默认 20M）、视频开关 `allow_video` 在后台「站点设置」，
   与进程级 `sapic_maxupload`（默认 25M，整个请求）是**两层限制**，两边都要放开才能传大文件。
3. 图片有效期：`image_expire_default_days`（未指定时的默认寿命）与 `image_expire_max_days`
   （单图上限）在后台「站点设置 → 上传」配置，单位天，`0` 表示永久 / 不限制；设了上限后不再允许
   永久图片。到期图片会在请求期被节流清理（每进程最多每 5 分钟一批），想更准时可加 cron：
   `flask sa purge-expired`（应用目录下、用部署用的 Python 执行）。
4. 邮件（注册验证、找回密码）在后台配置 SMTP；不配也能用，但相关功能不可用。
   端口决定传输方式：465/994 走隐式 SSL（不勾 STARTTLS），587 勾 STARTTLS，25 一般都不用。
   阿里/腾讯企业邮箱用 465 + 授权码（不是登录密码）。
5. 统一登录（OIDC）：`/admin/hooks` 启用 `passport`，填 `issuer` / `client_id` / `client_secret`；
   在 Passport 侧登记回调地址 `https://img.example.com/api/v2/auth/oidc/passport/callback`。
   站内首次登录会用 provider 的稳定标识（uid）建号，昵称只作显示名。
   关闭 `password_login` 后只能走统一登录，建议先给管理员账号绑定 OIDC 再关。
6. 存储后端：`up2local` 默认启用并自动创建 `local` 后端（写到 `STORAGE_DIR`）。要用云存储：
   ① 对应 SDK 已随 `base.txt` 安装，无需额外操作（第三方钩子才要自己装依赖）；② `/admin/hooks` 只负责启用该驱动
   （存储驱动的凭据不再在这里填）；③ 进 `/admin/backends` 编辑该后端，填写必填项（带 *，如 bucket /
   操作员 / 密码 / 加速域名），可用「检查」探测存储桶；④ 把它「上移」到第一位（或把优先级调到最小），
   之后新上传才会写到它。已有图片按副本所在后端读取，所以仍有副本的后端不允许禁用/删除。

## 7. 升级、备份与回滚

升级：

```bash
cd /srv/sapic && git pull
./.venv/bin/python -m pip install -r server/requirements/prod.txt
cd web && pnpm install && pnpm run build
systemctl restart sapic        # 启动时自动跑增量迁移
```

备份：

- 数据库：`pg_dump` / `mysqldump` / 直接拷 `sapic.db`（先停服务或 `sqlite3 .backup`）。
- 本地图片：`STORAGE_DIR` 整个目录。
- `server/.cfg`（密钥与 DSN）。

回滚：迁移幂等但不支持自动回退，回滚代码前先备份数据库；结构不兼容的版本需手工降级数据。

### 7.1 从 v1 迁移数据

v1 的数据在 Redis 里（`picbed:*` 键），文件在你那台 v1 部署的 `src/static/upload` 目录下
（v1 代码已从本仓库移除，看旧版本用 git tag）。迁移工具把它们写进 v2 的关系库与存储后端：

```bash
# 先看计划，不写任何东西
./.venv/bin/python tools/migrate_v1_to_v2.py --dry-run \
    --redis-url redis://127.0.0.1:6379/0 \
    --v1-upload-dir /srv/sapic-v1/src/static/upload

# 正式执行（默认读 server/.cfg 的 DATABASE_URL / STORAGE_DIR）
./.venv/bin/python tools/migrate_v1_to_v2.py \
    --redis-url redis://127.0.0.1:6379/0 \
    --v1-upload-dir /srv/sapic-v1/src/static/upload
```

v1 只用云存储（又拍云 / 七牛）时**没有本地目录，直接省略 `--v1-upload-dir`**：图片从 bucket
采纳、字节确实丢了的登记成外链，**不会**被跳过——`--skip-images` 是「只迁用户与相册」，
两者不是一回事。

用镜像部署时可以不开宿主机环境，直接在容器里跑（`tools/` 已打进镜像，工作目录就是 `/app`；
`redis-py` 不在运行时依赖里，临时装一次即可）：

```bash
docker compose run --rm --entrypoint sh sapic -c \
  'pip install -q redis && python /app/tools/migrate_v1_to_v2.py --dry-run \
     --redis-url redis://v1-redis:6379/0 --v1-upload-dir /v1-upload'
```

`--v1-upload-dir` 指向 v1 的目录，需要 `-v /srv/sapic-v1/src/static/upload:/v1-upload:ro`
把它挂进来；库与 `STORAGE_DIR` 走 compose 里的环境变量与数据卷。

- **幂等**：用户按 `username`、相册按 `(owner, name)`、图片按 `sha` 去重，中断后直接重跑，只补缺的部分。
- **sha 不变**：迁移保留 v1 的 `sha`，已发布的 `/raw/<sha>` 与直链继续有效。
- **文件走存储驱动**：原文件重新写进当前主后端（默认 `up2local` 的 `STORAGE_DIR`），不是简单搬目录；
  文件已丢失的图片会登记为外链（`source_url` 指向 v1 的 `src`），不会被丢弃。
- **v1 存在云存储（又拍云/七牛）时不会变成外链**：只要图片的 `src` 就在主后端的公开域名下，
  脚本直接把 bucket 里已有的对象登记成 `ok` 副本（`images_adopted`），不下载、不重传，
  删除时也会真正删掉对象；v1 的域名和现在配的不一样时，用 `--v1-src-prefix https://旧域名`
  告诉脚本按哪个前缀还原对象路径。
- **已经按旧版本迁过一遍、图片都成了外链**：不用清库重来——确认后端配好加速域名后，
  带着 `--refresh-external` 再跑一次，会把 `source_url` 的外链行就地补成 `ok` 副本（`images_adopted`）。
- **大小 / 类型 / 尺寸不再未知**：v1 把上传时的存储返回存在 `senders` 里（字节数在 `file-size`，
  有些版本只记 HTTP 的 `content-length`；另有 `width`/`height`/`content-md5`），脚本据此填
  `size`/`mime`/`width`/`height` 和副本 `etag`；早期跑出来 `0 B / 未知类型 / 未知` 的行，
  用 `--refresh-external` 重跑即可补齐（不需要重新上传）。
- **可见性**：v1 没有可见性概念、图片都是免登录直链，所以迁移出的相册与图片默认 `public`；
  需要收紧用 `--visibility private`（会同时改相册与图片，老直链随即失效）。
- 其余参数：`--only-user alice`、`--limit 100`、`--v2-db-url`、`--v2-storage-dir`；
  `--skip-images`（只迁用户与相册）、`--skip-users`（只迁图片）。
- **依赖**：数据库驱动复用应用依赖——PostgreSQL 走 `psycopg`（v3）、MySQL 走 `PyMySQL`，都在
  `server/requirements/base.txt` 里；工具没有单独的 requirements 文件，直接用仓库 `.venv` 运行。
- **redis-py 要单独装**：v2 应用不再依赖 Redis，只有这个工具要读 v1 的 `picbed:*` 键，
  现装的虚拟环境里没有就先 `pip install redis`（`server/requirements/dev.txt` 里有）。
- `--redis-url` 必填，`--v2-db-url` 省略时才用配置里的 `DATABASE_URL`。
- 有失败项时退出码为 `1`，清单里给出 sha 与原因；修复后重跑即可。
- 迁移前先停 v1 写入（或只读挂载 Redis），避免迁移期间新增图片没有进入快照。

### 7.2 客户端接入（PicGo / uPic / Typora / 右键菜单）

上传只有一个端点：`POST /api/v2/upload`（字段 `file` 或 `url`，可带 `album_id` / `title` / `expire`），
鉴权用 `Authorization: Bearer <PAT>`；PAT 在「设置 → 访问令牌」创建，勾选**上传图片**即可。

- 响应是 v2 信封，图片地址取 `data.image.src`，成功状态码为 `201`。
- **不接受仅凭 Cookie 的上传**：浏览器会话必须带 `X-CSRF-Token`，客户端带不了，所以请用 PAT。
- 站点关闭匿名上传且未带令牌时返回 `403 {"code":"FORBIDDEN","message":"anonymous upload is disabled"}`。

v1 的 `POST /api/upload` 兼容端点**已移除**：老配置（PicGo 的 `picbed` 字段、Typora 的 sapicli、
v1 的 LinkToken）都需要按 [快捷上传](docs/usage.md) 改一遍——逐项配置、可直接复制的脚本都在那一页。

## 8. 观测

- 健康检查：`GET /api/v2/health` → `{"status": "ok|degraded", "version", "database"}`，
  数据库不通返回 503。
- 日志：默认输出到 stdout（systemd 下 `journalctl -u sapic -f`）；日志级别用 `sapic_loglevel` 调。
- 每个请求都会带 `X-Request-Id`（也可由上游传入），排查时用它串日志。

## 9. 常见问题

| 现象 | 原因与处理 |
| --- | --- |
| 启动报 `SECRET_KEY must be configured in production` | 没配 `sapic_secretkey`，或 `sapic_env` 被设成了 `dev` |
| 启动报 `STORAGE_DIR must be an absolute path` | 用相对路径了，改成绝对路径 |
| 登录成功但刷新就掉线 | 反代没配 `X-Forwarded-Proto` + `sapic_proxyfix=1`，Cookie 的 `Secure` 与站点协议不一致 |
| 上传 413 | nginx `client_max_body_size`、`sapic_maxupload`、后台 `upload_image_max_size` / `upload_video_max_size` 取最小值 |
| 上传提示 `file type is not allowed` | 后台 `upload_allowed_ext` 白名单没放开该后缀 |
| 访问 `/raw/xxx` 404 | 图片被删除，或副本已不在对应后端（查 `image_backends.state`） |
| OIDC 回调 400 `invalid oidc state` | 回调域名/协议与发起时不一致（`sapic_proxyfix`、Passport 侧回调地址） |
| 前端刷新 404 | nginx 缺 `try_files $uri $uri/ /index.html` |
| 后台看不到钩子 | hooks 目录未被扫描（`HOOK_PKG_STORAGE_DIR`）或依赖未装，看日志里的 ImportError |
| 后台安装扩展报 `HOOK_PKG_STORAGE_DIR is not configured` | 该项被置空，填回目录（默认 `server/data/hooks`）并确保运行用户可写 |
| 钩子市场列表加载失败 | 出网被拦或 GitHub 不可达；用 `sapic_hookmarketurl` 指向镜像，或在市场页「手动安装」直接填包名 |
