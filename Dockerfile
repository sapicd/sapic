FROM python:3.6.10-alpine3.11
MAINTAINER staugur <staugur@saintic.com>
ADD src /picbed
ADD requirements /requirements
RUN sed -i 's/dl-cdn.alpinelinux.org/mirrors.tuna.tsinghua.edu.cn/g' /etc/apk/repositories && \
    apk add --no-cache gcc musl-dev libffi-dev make && \
    pip install --timeout 30 --index https://pypi.tuna.tsinghua.edu.cn/simple -r /requirements/all.txt
WORKDIR /picbed
ENTRYPOINT ["sh", "online_gunicorn.sh", "run"]