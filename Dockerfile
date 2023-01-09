FROM python:3.8-alpine
LABEL maintainer=me@tcw.im
ARG PIPMIRROR=https://pypi.org/simple
ARG ALPINEMIRROR=dl-cdn.alpinelinux.org
ENV sapic_isrun=true
COPY requirements /requirements
RUN sed -i "s/dl-cdn.alpinelinux.org/${ALPINEMIRROR}/g" /etc/apk/repositories && \
    apk upgrade --no-cache && \
    apk add --no-cache libgcc libstdc++ gcompat && \
    pip install --upgrade pip && \
    pip install --timeout 30 --index $PIPMIRROR --user --no-cache-dir --no-warn-script-location -r /requirements/all.txt && \
    LOCAL_PKG="/root/.local" && \
    ln -sf ${LOCAL_PKG}/bin/flask ${LOCAL_PKG}/bin/gunicorn /bin/ && \
    ln -sf $(which python) /python && \
    sed -i "s#$(which python)#/python#" /bin/gunicorn
WORKDIR /picbed
COPY src /picbed
EXPOSE 9514
ENTRYPOINT ["gunicorn", "app:app", "-c", "sapicd.py"]
