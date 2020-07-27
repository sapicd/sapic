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
ARG PIPMIRROR=https://pypi.tuna.tsinghua.edu.cn/simple
COPY requirements /requirements
RUN pip install --timeout 30 --index $PIPMIRROR --user --no-cache-dir --no-warn-script-location -r /requirements/all.txt

# -- app environment --
FROM base
ENV LOCAL_PKG="/root/.local"
ENV picbed_isrun=true
COPY --from=build ${LOCAL_PKG} ${LOCAL_PKG}
RUN ln -sf ${LOCAL_PKG}/bin/flask ${LOCAL_PKG}/bin/gunicorn /bin/ && \
    ln -sf $(which python) /python && \
    sed -i "s#$(which python)#/python#" /bin/gunicorn
COPY src /picbed
ENTRYPOINT ["gunicorn", "app:app", "-c", "picbed.py"]