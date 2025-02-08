# -- build and run with debian(multiarch) --
FROM python:3.10-slim
LABEL maintainer=me@tcw.im
ARG PIPMIRROR=https://pypi.org/simple
ENV sapic_isrun=true
COPY requirements /requirements
RUN pip install --timeout 30 --index $PIPMIRROR --user --no-cache-dir --no-warn-script-location -r /requirements/all.txt && \
    ln -sf /root/.local/bin/flask /root/.local/bin/gunicorn /bin/ && \
    ln -sf $(which python) /python && \
    sed -i "s#$(which python)#/python#" /bin/gunicorn
WORKDIR /picbed
COPY src /picbed
EXPOSE 9514
ENTRYPOINT ["gunicorn", "app:app", "-c", "sapicd.py"]