# syntax=docker/dockerfile:1

# ---- 1. 前端构建 ------------------------------------------------------------
FROM node:23-alpine AS web

WORKDIR /app/web
RUN corepack enable && corepack prepare pnpm@8.14.1 --activate

#: 先只装依赖，改源码时能命中缓存。
COPY web/package.json web/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY web/ ./
RUN pnpm run build


# ---- 2. 运行镜像 ------------------------------------------------------------
FROM python:3.12-slim

#: 后台任务（到期清理 / 审核扫描 / 演示账号改密）由 supervisor 拉起的独立进程
#: `flask sa scheduler` 负责；web worker 固定 sapic_scheduler=0，不在进程内抢锁。
#: 这样 worker 滚动重启不会打断调度，后台页面也能稳定看到同一个调度者。
#: FLASK_APP 供 entrypoint 的 `flask sa upgrade` 与调度进程使用（镜像里不走 Makefile）。
#: gunicorn 参数集中在 server/sapicd.py，由 supervisor 直接传给 gunicorn。
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_APP=sapic \
    sapic_env=prod \
    sapic_scheduler=0 \
    SAPIC_HTTP_PORT=80

#: procps 只提供 ps / top 等排查工具：supervisor 管着 web / scheduler / nginx 三个进程，
#: 容器里 `docker exec sapic ps -ef` 能直接看出谁在跑、调度进程是否存活。
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates curl nginx procps supervisor tini \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

#: 先装依赖再拷代码，后端改动不会让 pip 层失效。
COPY server/requirements/ /app/server/requirements/
RUN pip install --no-cache-dir -r /app/server/requirements/prod.txt

COPY server/ /app/server/
#: 运维脚本（v1 数据迁移等）随镜像发布，容器里可直接跑 /app/tools/*.py。
COPY tools/ /app/tools/
COPY --from=web /app/web/dist /app/web/dist

#: nginx 用仓库里的完整主配置模板：worker 数、端口是占位符，由 entrypoint 按
#: SAPIC_NGINX_WORKERS / SAPIC_HTTP_PORT 渲染到 /etc/nginx/nginx.conf。
#: nginx 自身的访问/错误日志都关掉，不再依赖镜像自带配置或日志软链。
COPY docker/nginx.conf /etc/nginx/nginx.conf.template
COPY docker/entrypoint.sh /usr/local/bin/sapic-entrypoint
#: supervisor 统管 web / scheduler / nginx：web 直接跑 gunicorn 并加载
#: server/sapicd.py，scheduler 直接跑 `python -m flask sa scheduler`，
#: 都不再经过 shell wrapper。配置落在 /etc/supervisord.conf：这是 supervisorctl
#: 默认搜索的路径之一，容器里不用带 -c 就能直接 `supervisorctl status`。
COPY docker/supervisord.conf /etc/supervisord.conf
RUN chmod 0755 /usr/local/bin/sapic-entrypoint \
    && mkdir -p /app/server/data

#: 数据库（默认 SQLite）、上传文件与第三方钩子包都在这里，务必挂卷。
VOLUME ["/app/server/data"]
#: 默认 80；改端口用 -e SAPIC_HTTP_PORT=8080（EXPOSE 只是文档，不影响实际监听）。
EXPOSE 80

#: 首次启动要建表/跑迁移，留足 40s，避免刚起来的容器被判定为不健康。
#: 用 shell 形式才能在运行时展开 SAPIC_HTTP_PORT。
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${SAPIC_HTTP_PORT:-80}/api/v2/health" || exit 1

ENTRYPOINT ["/usr/bin/tini", "-g", "--"]
CMD ["/usr/local/bin/sapic-entrypoint"]
