# 快速开始

目标：几分钟内让 sapic 跑起来，并传上第一张图。只想看看效果就走 Docker，要改代码或长期运行就走
源码方式；systemd、nginx、HTTPS、数据库选择这些生产细节见[部署与运维](deploy.md)。

## 方式一：Docker（最快）

```bash
docker compose up -d          # single container + SQLite; maps host port 80 into the container
```

镜像里已经包含 gunicorn + nginx + 构建好的前端，浏览器打开 `http://<服务器IP>/` 就是站点。
SQLite 库、上传文件与第三方钩子都在 `sapic-data` 卷里，删容器不丢数据。

换成自己的域名、并换掉内置密钥：

```bash
SAPIC_BASE_URL='https://img.example.com' \
SAPIC_SECRET_KEY="$(openssl rand -hex 32)" docker compose up -d
```

端口冲突时用 `SAPIC_PORT=8080 docker compose up -d`。要用 PostgreSQL（多进程 / 多副本）或部署到
Kubernetes，看[容器与编排](deploy.md)。

## 方式二：源码运行

```bash
git clone https://github.com/sapicd/sapic && cd sapic

# deps: backend into the repo-root .venv; the front end is a separate pnpm project
python3 -m venv .venv && ./.venv/bin/python -m pip install -r server/requirements/dev.txt
(cd web && pnpm install)

# create an admin (the defaults are SQLite + a built-in secret; no config file yet)
(cd server && FLASK_APP=sapic ../.venv/bin/python -m flask sa create-admin -u admin -p 'your-password')

# backend on 0.0.0.0:9514, reloads on change
(cd server && FLASK_APP=sapic sapic_env=dev ../.venv/bin/python -m flask run --host 0.0.0.0 --port 9514 --reload)

# another terminal: front end on 127.0.0.1:5173, proxying /api and /raw/ to 9514
(cd web && pnpm run dev)
```

开发时访问 <http://127.0.0.1:5173>（有热更新）。只起后端的话，9514 上只有 JSON 接口，没有页面。

## 传第一张图

1. 用刚建的管理员账号登录，进后台 `/admin/setting` 按需打开注册、匿名上传，调整单文件上限；
2. 首页拖拽或粘贴图片上传，点结果里的地址确认能打开；
3. 「设置 → 访问令牌」建一枚只含「上传图片」的 PAT —— PicGo / Typora / 脚本都用它，
   逐项配置见[快捷上传](usage.md)。

## 接下来

- 部署到自己的服务器（systemd、nginx、HTTPS、备份）：[部署与运维](deploy.md)
- 每个配置项与站点设置的含义：[配置](config.md)
- 从 v1 升级：[从 v1 迁移数据](migrate-v1.md)
- 起不来、传不上：[常见问题](faq.md)
