#!/bin/bash
# 单容器启动：gunicorn（127.0.0.1:9514） + nginx（默认 :80，可用 SAPIC_HTTP_PORT 改）。
# tini -g 负责把容器信号广播给整个进程组，这里只维护两个子进程的生命周期。
set -euo pipefail

if [ -z "${sapic_secretkey:-}" ]; then
    echo "[sapic] sapic_secretkey is required (env or server/.cfg)" >&2
    exit 1
fi

export sapic_env="${sapic_env:-prod}"
WORKERS="${WEB_CONCURRENCY:-4}"

#: 容器内 nginx 的监听端口：默认 80，便于和宿主/外层反代保持同一约定；
#: 需要在非 root 端口或同 Pod 多容器共存时改它，镜像里的 nginx.conf 是模板，
#: 占位符在这里替换后再落到 conf.d，避免把端口写死进镜像。
HTTP_PORT="${SAPIC_HTTP_PORT:-80}"
case "${HTTP_PORT}" in
    '' | *[!0-9]*)
        echo "[sapic] SAPIC_HTTP_PORT must be a number, got '${HTTP_PORT}'" >&2
        exit 1
        ;;
esac
if [ "${HTTP_PORT}" -lt 1 ] || [ "${HTTP_PORT}" -gt 65535 ]; then
    echo "[sapic] SAPIC_HTTP_PORT out of range (1-65535): ${HTTP_PORT}" >&2
    exit 1
fi
sed "s|__LISTEN_PORT__|${HTTP_PORT}|g" /etc/nginx/sapic.conf.template \
    > /etc/nginx/conf.d/default.conf

cd /app/server
echo "[sapic] starting gunicorn with ${WORKERS} workers"
gunicorn "sapic:create_app()" \
    --bind 127.0.0.1:9514 \
    --workers "${WORKERS}" \
    --worker-class gevent \
    --timeout 60 \
    --access-logfile - \
    --error-logfile - &
GUNICORN_PID=$!

NGINX_PID=""
term() {
    kill -TERM "${GUNICORN_PID}" ${NGINX_PID:+"${NGINX_PID}"} 2>/dev/null || true
    wait "${GUNICORN_PID}" 2>/dev/null || true
}
trap term TERM INT

#: 启动期等一会儿：数据库连不上时 gunicorn 会直接退出，早失败比 502 好排查。
sleep 2
if ! kill -0 "${GUNICORN_PID}" 2>/dev/null; then
    echo "[sapic] gunicorn exited during startup, check sapic_db_url / sapic_secretkey" >&2
    exit 1
fi

echo "[sapic] starting nginx on :${HTTP_PORT}"
nginx -g 'daemon off;' &
NGINX_PID=$!

wait "${NGINX_PID}"
