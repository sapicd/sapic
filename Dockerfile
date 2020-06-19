# -- base python --
FROM python:3.7-alpine AS base
LABEL maintainer=staugur@saintic.com
RUN mkdir /picbed/
WORKDIR /picbed

# -- build dependencies --
FROM python:3.7-slim AS build
ARG PIPMIRROR=https://pypi.tuna.tsinghua.edu.cn/simple
COPY requirements /requirements
RUN  pip install --timeout 30 --index $PIPMIRROR --user --no-cache-dir --no-warn-script-location -r /requirements/all.txt

# -- app environment --
FROM base
ENV LOCAL_PKG="/root/.local"
COPY --from=build ${LOCAL_PKG} ${LOCAL_PKG}
RUN ln -sf ${LOCAL_PKG}/bin/flask ${LOCAL_PKG}/bin/gunicorn /usr/local/bin/
COPY src /picbed
ENTRYPOINT ["sh", "online_gunicorn.sh", "run"]
