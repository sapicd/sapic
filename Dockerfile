# -- build dependencies with debian(multiarch) --
FROM python:3.8-slim AS build
LABEL maintainer=me@tcw.im
ARG PIPMIRROR=https://pypi.org/simple
COPY requirements /requirements
RUN pip install --timeout 30 --index $PIPMIRROR --user --no-cache-dir --no-warn-script-location -r /requirements/all.txt

# -- app environment(multiarch) --
FROM python:3.8-alpine
ARG ALPINEMIRROR=dl-cdn.alpinelinux.org
ENV sapic_isrun=true
COPY --from=build /root/.local /root/.local
RUN apk upgrade --no-cache && \
    apk add --no-cache libgcc libstdc++ gcompat && \
    pip install --no-cache-dir --user -U pip pillow && \
    ln -sf /root/.local/bin/flask /root/.local/bin/gunicorn /bin/ && \
    ln -sf $(which python) /python && \
    sed -i "s#$(which python)#/python#" /bin/gunicorn
WORKDIR /picbed
COPY src /picbed
EXPOSE 9514
ENTRYPOINT ["gunicorn", "app:app", "-c", "sapicd.py"]