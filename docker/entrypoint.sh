#!/bin/bash
# 单容器启动：初始化密钥与 nginx 配置，跑一次迁移，然后交给 supervisor 统管
# gunicorn（127.0.0.1:9514）、独立调度进程与 nginx（默认 :80）。
set -euo pipefail

#: 未显式传 sapic_secretkey 时生成一次随机密钥并留在数据卷里：容器重启、
#: 多副本共用一个卷时都沿用同一把；删掉它等于吊销全部会话（Cookie 用它对内容
#: 签名）。显式传了环境变量的部署不受影响。
SECRET_FILE="${SAPIC_SECRET_FILE:-/app/server/data/secret_key}"
if [ -z "${sapic_secretkey:-}" ]; then
    if [ -s "${SECRET_FILE}" ]; then
        sapic_secretkey="$(cat "${SECRET_FILE}")"
    else
        sapic_secretkey="$(od -An -tx1 -N32 /dev/urandom | tr -d ' \n')"
        mkdir -p "$(dirname "${SECRET_FILE}")"
        if ! (umask 077 && printf '%s\n' "${sapic_secretkey}" > "${SECRET_FILE}") 2>/dev/null; then
            echo "[sapic] warning: cannot write ${SECRET_FILE}, sessions will be revoked on restart" >&2
        fi
        echo "[sapic] generated sapic_secretkey (${SECRET_FILE})"
    fi
    export sapic_secretkey
fi

export sapic_env="${sapic_env:-prod}"

#: 容器内 nginx 的监听端口：默认 80，便于和宿主/外层反代保持同一约定；
#: 需要在非 root 端口或同 Pod 多容器共存时改它。仓库里的 docker/nginx.conf 是
#: 完整主配置模板，占位符在这里替换后写到 /etc/nginx/nginx.conf。
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
#: nginx worker 数：默认 auto（按 CPU 核数），设正整数可固定；和 sapic_workers
#: 是两件事——前者管静态资源/反代，后者管 gunicorn 应用 worker。这里只做校验，
#: 模板里的 __NGINX_WORKERS__ 由下面的渲染一起替换。
NGINX_WORKERS="${SAPIC_NGINX_WORKERS:-auto}"
case "${NGINX_WORKERS}" in
    auto) ;;
    '' | *[!0-9]*)
        echo "[sapic] SAPIC_NGINX_WORKERS must be 'auto' or a positive number, got '${NGINX_WORKERS}'" >&2
        exit 1
        ;;
esac
if [ "${NGINX_WORKERS}" != "auto" ] && [ "${NGINX_WORKERS}" -lt 1 ]; then
    echo "[sapic] SAPIC_NGINX_WORKERS must be at least 1" >&2
    exit 1
fi

#: nginx 的访问日志与错误日志都在模板里关掉，容器日志只留应用自身输出。
sed -e "s|__NGINX_WORKERS__|${NGINX_WORKERS}|g" \
    -e "s|__LISTEN_PORT__|${HTTP_PORT}|g" \
    /etc/nginx/nginx.conf.template > /etc/nginx/nginx.conf
if grep -q '__[A-Z_]*__' /etc/nginx/nginx.conf; then
    echo "[sapic] unresolved placeholder in /etc/nginx/nginx.conf" >&2
    exit 1
fi

cd /app/server
#: 迁移先在这里同步跑一遍：supervisor 里的 web 与 scheduler 是两个进程，若都靠
#: create_app 的自动迁移，同时启动时会在同一个库上撞车。失败就直接退出，比
#: 两个子进程各报一次错好排查。
echo "[sapic] applying migrations"
flask sa upgrade

#: 交给 supervisor 统管三个进程（web / scheduler / nginx）；tini -g 负责把容器
#: 信号广播给整个进程组，supervisord 再有序停子进程。
echo "[sapic] starting supervisord (web + scheduler + nginx on :${HTTP_PORT})"
exec supervisord -c /etc/supervisord.conf -n
