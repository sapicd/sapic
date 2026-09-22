# -- build and run with debian(multiarch) --
FROM python:3.12-slim-bookworm
LABEL maintainer=me@tcw.im
ARG PIPMIRROR=https://pypi.org/simple
ENV sapic_isrun=true
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update -o Acquire::Retries=3 && \
    apt-get install -y --no-install-recommends -o Acquire::Retries=3 git && \
    rm -rf /var/lib/apt/lists/*
COPY requirements /requirements
RUN pip install --timeout 15 --retries 3 --index $PIPMIRROR --user --no-cache-dir --no-warn-script-location -r /requirements/all.txt && \
    ln -sf /root/.local/bin/flask /root/.local/bin/gunicorn /bin/
WORKDIR /picbed
COPY src /picbed
EXPOSE 9514
ENTRYPOINT ["gunicorn", "app:app", "-c", "sapicd.py"]