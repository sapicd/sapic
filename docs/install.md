# 安装与部署

## 环境要求

| 组件 | 要求 | 说明 |
| --- | --- | --- |
| Python | 3.10+ | 后端 `server/`，包名 `sapic`（纯本地包，不做 `pip install`） |
| Node.js | 23 + pnpm 8 | 只在构建 / 开发前端时需要 |
| 数据库 | PostgreSQL / MySQL / SQLite | 由 `sapic_db_url` 指定，默认 SQLite（`data/sapic.db`） |

依赖由 `server/requirements/` 管理：`base.txt`（运行时，含内置钩子用到的 requests / Pillow /
七牛 / 又拍云 SDK）、`dev.txt`（测试）、`prod.txt`（base + gunicorn + gevent）。第三方钩子是
独立的 pip 包，自带自己的依赖。

## 源码运行

```bash
# 依赖：后端装进仓库根的 .venv，前端是独立的 pnpm 工程
python3 -m venv .venv && ./.venv/bin/python -m pip install -r server/requirements/dev.txt
(cd web && pnpm install)

# 确认配置（打印默认值合并后的结果，检查 DATABASE_URL / STORAGE_DIR）
(cd server && ../.venv/bin/python -c "import json; from sapic.basis.conf import load_config; print(json.dumps(load_config(), indent=2, ensure_ascii=False))")

# 创建管理员（刚 clone 下来用默认配置即可：SQLite + 内置密钥）
(cd server && FLASK_APP=sapic ../.venv/bin/python -m flask sa create-admin -u admin -p '你的密码')

# 开发服务器：0.0.0.0:9514，改代码自动重载
(cd server && FLASK_APP=sapic sapic_env=dev ../.venv/bin/python -m flask run --host 0.0.0.0 --port 9514 --reload)
```

前端开发服务器单独启动，`/api` 与 `/raw/` 会代理到 9514：

```bash
(cd web && pnpm run dev)     # 127.0.0.1:5173
```

```{note}
以上都是真实命令，容器或没有 `make` 的机器可以直接照做。仓库根的 `Makefile` 只是本地开发的
便利封装（`make setup` / `make dev` / `make serve` 等与它们一一对应），**部署脚本里不要依赖它**。
```

生产用 gunicorn（`-k gevent`，worker 数按 CPU 核数调）：

```bash
./.venv/bin/python -m pip install -r server/requirements/prod.txt
cd server && ../.venv/bin/python -m gunicorn "sapic:create_app()" -b 0.0.0.0:9514 -w 8 -k gevent
```

```{note}
`sapic_secretkey` **不是必填项**：内置默认密钥长度足够，单机自用不必配置。
但它在开源代码里是公开串，**公网多用户**站点建议换掉（`server/.cfg` 或环境变量，
至少 14 字节，`openssl rand -hex 32` 即可），否则读过源码的人能伪造会话 Cookie。
```

## 容器与编排

仓库根提供三种产物，均在构建镜像时完成前端构建：

```bash
docker build -t sapic:local .                          # 镜像内已完成前端构建
docker compose up -d                                   # 单容器 + SQLite
kubectl apply -f kube-sapic.yaml                       # 集群清单
```

镜像由 GitHub Actions 发布：`master` → `latest`，`dev` → `dev`，`v*` tag → semver 标签。

## 升级

- 启动时会自动执行 `sapic/migrations` 里的幂等迁移（`auto_upgrade()`）；
  手动兜底命令是 `cd server && FLASK_APP=sapic ../.venv/bin/python -m flask sa upgrade`。
- 图片有效期清理除了定时兜底（`before_request` 每进程 5 分钟节流），
  还可由运维命令触发：`flask sa purge-expired`。
- 从 v1 迁移数据用 `tools/migrate_v1_to_v2.py`：读 v1 Redis，写入 `users` / `albums` /
  `images` / `image_backends`，保留原 sha（`/raw/<sha>` 老链接继续有效），幂等并支持
  `--dry-run`。本地文件通过存储驱动重传（v1 只用云存储、没有本地目录时省略
  `--v1-upload-dir`）；v1 存在云存储（又拍云 / 七牛）时，`src` 已在主后端
  公开域名下的对象**原地采纳**（不下载、不重传，`--v1-src-prefix` 处理旧域名），大小 / 类型 /
  尺寸从 v1 的 `senders` 记录里回填，只有字节真的丢了才登记外链。用法见 `DEPLOY.md` 第 7 节。
- 该工具的依赖：数据库驱动复用 `server/requirements/base.txt`（PostgreSQL 走 `psycopg` v3、
  MySQL 走 `PyMySQL`），但 **redis-py 不在应用依赖里**（v2 运行时不用 Redis），
  现装的环境没有时先 `pip install redis`（`dev.txt` 里已包含）。
- v1 的客户端配置要改一次：上传端点统一为 `POST /api/v2/upload`（字段 `file`，
  响应取 `data.image.src`），v1 的 `/api/upload` 兼容层已移除；
  PicGo / uPic / Typora / 右键菜单的逐项配置见[快捷上传](usage.md)。

## 反向代理

- 请求体上限是**三层取最小值**：nginx 的 `client_max_body_size`、进程级
  `sapic_maxupload`（映射 `MAX_CONTENT_LENGTH`）、站点设置里按媒体类型的单文件上限
  （`upload_image_max_size` / `upload_video_max_size`）。multipart 有额外开销，
  进程级上限要比站点上限略大。
- 部署在代理之后时打开 `sapic_proxyfix=1`，`/raw` 与生成的直链才会用对外的
  scheme / host。

## 客户端接入

PicGo、uTools、Typora、Windows / macOS 右键菜单与油猴脚本的配置方式和配套脚本，
统一整理在 [快捷上传](usage.md)：所有客户端都用访问令牌（PAT）鉴权，
令牌在「设置 → 访问令牌」创建，只勾「上传图片」即可。
