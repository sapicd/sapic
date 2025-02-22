# -- build and run with debian(multiarch) --
FROM python:3.12-slim-bullseye
LABEL maintainer=me@tcw.im
ARG PIPMIRROR=https://pypi.org/simple
ENV sapic_isrun=true
COPY requirements /requirements
RUN apt update && apt install -y git && \
    pip install --timeout 15 --index $PIPMIRROR --user --no-cache-dir --no-warn-script-location -r /requirements/all.txt && \
    ln -sf /root/.local/bin/flask /root/.local/bin/gunicorn /bin/
WORKDIR /picbed
COPY src /picbed
EXPOSE 9514
ENTRYPOINT ["gunicorn", "app:app", "-c", "sapicd.py"]