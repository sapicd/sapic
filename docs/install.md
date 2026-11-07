# 安装与部署

## 环境要求

| 组件 | 要求 | 说明 |
| --- | --- | --- |
| Python | 3.10+ | 后端 `server/`，包名 `sapic`（纯本地包，不做 `pip install`） |
| Node.js | 20 + pnpm 8 | 只在构建 / 开发前端时需要 |
| 数据库 | PostgreSQL / MySQL / SQLite | 由 `sapic_db_url` 指定，默认 SQLite（`data/sapic.db`） |
| Redis | 可选 | v2 不依赖 Redis 存业务数据 |

依赖由 `server/requirements/` 管理：`base.txt`（运行时，含内置钩子用到的 requests / Pillow /
七牛 / 又拍云 SDK）、`dev.txt`（测试）、`prod.txt`（base + gunicorn + gevent）。第三方钩子是
独立的 pip 包，自带自己的依赖。

## 源码运行

```bash
make setup        # 后端 dev.txt + 前端 pnpm install
make config       # 打印当前生效配置，确认 DATABASE_URL / STORAGE_DIR
make create-admin U=admin P='你的密码'
make dev          # 0.0.0.0:9514，改代码自动重载
```

前端开发服务器单独启动，`/api` 与 `/raw/` 会代理到 9514：

```bash
make web-dev      # 127.0.0.1:5173
```

生产用 gunicorn（`WORKERS=4 -k gevent`）：

```bash
make install-prod
sapic_secretkey="$(openssl rand -hex 32)" make serve WORKERS=8
```

```{important}
生产模式必须显式配置 `sapic_secretkey`（`server/.cfg` 或环境变量，至少 14 字节）。
内置默认密钥是公开字符串，用它在生产启动会被 `load_config()` 直接断言拦下。
```

## 容器与编排

仓库根提供三种产物，均在构建镜像时完成前端构建：

```bash
make docker                        # 构建 sapic:local
docker compose up -d               # 需 SAPIC_SECRET_KEY
kubectl apply -f kube-sapic.yaml   # 集群清单
```

镜像由 GitHub Actions 发布：`master` → `latest`，`dev` → `dev`，`v*` tag → semver 标签。

## 升级

- 启动时会自动执行 `sapic/migrations` 里的幂等迁移（`auto_upgrade()`）；
  `make upgrade` 是手动兜底，等价于 `flask sa upgrade`。
- 图片有效期清理除了定时兜底（`before_request` 每进程 5 分钟节流），
  还可由运维命令触发：`flask sa purge-expired`。
- 从 v1 迁移数据用 `tools/migrate_v1_to_v2.py`：读 v1 Redis，写入 `users` / `albums` /
  `images` / `image_backends`，保留原 sha（`/raw/<sha>` 老链接继续有效），幂等并支持
  `--dry-run`；文件通过存储驱动重传，源文件缺失时登记为外链。用法见 `DEPLOY.md` 第 7 节。
- v1 客户端（PicGo / uPic / Typora）继续用 `POST /api/upload`，响应是 v1 信封；
  鉴权可用 `token` / `X-Token` 表单字段传 PAT（不是 v1 的 LinkToken）。

## 反向代理

- 请求体上限是**三层取最小值**：nginx 的 `client_max_body_size`、进程级
  `sapic_maxupload`（映射 `MAX_CONTENT_LENGTH`）、站点设置里按媒体类型的单文件上限
  （`upload_image_max_size` / `upload_video_max_size`）。multipart 有额外开销，
  进程级上限要比站点上限略大。
- 部署在代理之后时打开 `sapic_proxyfix=1`，`/raw` 与生成的直链才会用对外的
  scheme / host。
