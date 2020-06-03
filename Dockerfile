FROM python:3.6.10-alpine3.11
LABEL maintainer=staugur@saintic.com
ARG ALPINEMIRROR=mirrors.tuna.tsinghua.edu.cn
ARG PIPMIRROR=https://pypi.tuna.tsinghua.edu.cn/simple
RUN mkdir /picbed/
WORKDIR /picbed
COPY requirements /picbed/requirements
RUN sed -i "s/dl-cdn.alpinelinux.org/$ALPINEMIRROR/g" /etc/apk/repositories && \
    apk add --no-cache gcc musl-dev libffi-dev make && \
    pip install --timeout 30 --index $PIPMIRROR -r requirements/all.txt
COPY src /picbed
ENTRYPOINT ["sh", "online_gunicorn.sh", "run"]