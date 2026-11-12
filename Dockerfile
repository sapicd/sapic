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

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    sapic_env=prod \
    SAPIC_HTTP_PORT=80

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates curl nginx tini \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

#: 先装依赖再拷代码，后端改动不会让 pip 层失效。
COPY server/requirements/ /app/server/requirements/
RUN pip install --no-cache-dir -r /app/server/requirements/prod.txt

COPY server/ /app/server/
#: 运维脚本（v1 数据迁移等）随镜像发布，容器里可直接跑 /app/tools/*.py。
COPY tools/ /app/tools/
COPY --from=web /app/web/dist /app/web/dist

#: nginx 配置是模板（含端口占位符），由 entrypoint 按 SAPIC_HTTP_PORT 渲染到
#: /etc/nginx/conf.d/default.conf；镜像里不放成品 conf，端口才不写死。
COPY docker/nginx.conf /etc/nginx/sapic.conf.template
COPY docker/entrypoint.sh /usr/local/bin/sapic-entrypoint
RUN chmod 0755 /usr/local/bin/sapic-entrypoint \
    && rm -f /etc/nginx/sites-enabled/default \
    && mkdir -p /app/server/data \
    && ln -sf /dev/stdout /var/log/nginx/access.log \
    && ln -sf /dev/stderr /var/log/nginx/error.log

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
