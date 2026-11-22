# 安装与部署

本文只讲「怎么把 sapic 跑起来」：环境要求、源码运行、生产入口与升级方式。
只想尽快跑起来看效果，走[快速开始](quickstart.md)更短。
生产部署的完整命令（gunicorn + systemd + nginx、容器与编排、数据库、备份回滚）见
[部署与运维](deploy.md)，配置项的含义见[配置](config.md)。

## 环境要求

| 组件 | 要求 | 说明 |
| --- | --- | --- |
| Python | 3.10+ | 后端 `server/`，包名 `sapic`（纯本地包，不做 `pip install`） |
| Node.js | 23+、pnpm 8 | 只在构建 / 开发前端时需要 |
| 数据库 | PostgreSQL / MySQL / SQLite | 由 `sapic_db_url` 指定，默认 SQLite（`server/data/sapic.db`） |

依赖由 `server/requirements/` 管理：`base.txt`（运行时，含内置钩子用到的 requests / Pillow /
七牛 / 又拍云 SDK）、`dev.txt`（base + 测试）、`prod.txt`（base + gunicorn + gevent + setproctitle）。
第三方钩子是独立的 pip 包，自带自己的依赖。

## 源码运行

```bash
# deps: backend into the repo-root .venv; the front end is a separate pnpm project
python3 -m venv .venv && ./.venv/bin/python -m pip install -r server/requirements/dev.txt
(cd web && pnpm install)

# inspect the effective config (defaults merged; check DATABASE_URL / STORAGE_DIR)
(cd server && ../.venv/bin/python -c "import json; from sapic.basis.conf import load_config; print(json.dumps(load_config(), indent=2, ensure_ascii=False))")

# create an admin (a fresh clone runs on the defaults: SQLite + built-in secret)
(cd server && FLASK_APP=sapic ../.venv/bin/python -m flask sa create-admin -u admin -p 'your-password')

# dev server on 0.0.0.0:9514, reloads on change
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

## 生产运行

装上生产依赖后用 gunicorn 起后端（worker 数按 CPU 核数调）：

```bash
./.venv/bin/python -m pip install -r server/requirements/prod.txt
cd server && ../.venv/bin/python -m gunicorn "sapic:create_app()" -b 127.0.0.1:9514 -w 4 -k gevent --name sapic
```

systemd 单元、nginx 站点（含 `sapic_proxyfix` 与 TLS 透传）、容器与集群编排、数据库选择见
[部署与运维](deploy.md)。

```{note}
`sapic_secretkey` **不是必填项**：内置默认密钥长度足够，单机自用不必配置。
但它在开源代码里是公开串，**公网多用户**站点建议换掉（`server/.cfg` 或环境变量，
至少 14 字节，`openssl rand -hex 32` 即可），否则读过源码的人能伪造会话 Cookie。
```

## 升级

- 启动时会自动执行 `sapic/migrations` 里的幂等迁移（`auto_upgrade()`）；
  手动兜底命令是 `cd server && FLASK_APP=sapic ../.venv/bin/python -m flask sa upgrade`。
- 图片有效期清理除了定时兜底（`before_request` 每进程 5 分钟节流），
  还可由运维命令触发：`flask sa purge-expired`。
- 拉代码、装依赖、重建前端与重启服务的完整流程，以及备份与回滚见[部署与运维](deploy.md)；
  从 v1 迁移数据见[从 v1 迁移数据](migrate-v1.md)。

## 客户端接入

PicGo、uTools、Typora、Windows / macOS 右键菜单与油猴脚本的配置方式和配套脚本，
统一整理在 [快捷上传](usage.md)：所有客户端都用访问令牌（PAT）鉴权，
令牌在「设置 → 访问令牌」创建，只勾「上传图片」即可。
