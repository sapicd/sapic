# -- base python --
FROM python:3.7-alpine AS base
LABEL maintainer=staugur@saintic.com
WORKDIR /picbed

# -- build dependencies with alpine --
#FROM python:3.7-alpine AS build
#ARG ALPINEMIRROR=mirrors.tuna.tsinghua.edu.cn
#ARG PIPMIRROR=https://pypi.tuna.tsinghua.edu.cn/simple
#RUN sed -i "s/dl-cdn.alpinelinux.org/$ALPINEMIRROR/g" /etc/apk/repositories && \
#    apk add --no-cache gcc musl-dev libffi-dev make && \
#    rm -fr /var/cache/apk/*
#COPY requirements /requirements
#RUN pip install --timeout 30 --index $PIPMIRROR --user --no-cache-dir --no-warn-script-location -r /requirements/all.txt

# -- build dependencies with debian --
FROM python:3.7-slim AS build
ARG DEBIANMIRROR=mirrors.tuna.tsinghua.edu.cn
ARG PIPMIRROR=https://pypi.tuna.tsinghua.edu.cn/simple
RUN sed -i "s@deb.debian.org@${DEBIANMIRROR}@g" /etc/apt/sources.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends build-essential && \
    apt-get clean && rm -rf /var/lib/apt/lists/*
COPY requirements /requirements
RUN pip install --timeout 30 --index $PIPMIRROR --user --no-cache-dir --no-warn-script-location -r /requirements/all.txt

# -- app environment --
FROM base
ENV LOCAL_PKG="/root/.local"
COPY --from=build ${LOCAL_PKG} ${LOCAL_PKG}
RUN ln -sf ${LOCAL_PKG}/bin/flask ${LOCAL_PKG}/bin/gunicorn /usr/local/bin/
COPY src /picbed
ENTRYPOINT ["sh", "online_gunicorn.sh", "run"]
