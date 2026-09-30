FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    KIDSCONTROL_DATA_DIR=/data \
    HOST=0.0.0.0 \
    PORT=8000

RUN groupadd --system kidscontrol && useradd --system --gid kidscontrol --home-dir /nonexistent --shell /usr/sbin/nologin kidscontrol
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends openssh-client ca-certificates && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY client ./client

COPY docker/entrypoint.sh /usr/local/bin/kidscontrol-entrypoint
RUN chmod 0755 /usr/local/bin/kidscontrol-entrypoint && mkdir /data && chown kidscontrol:kidscontrol /data

USER kidscontrol
EXPOSE 8000
VOLUME ["/data"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import json,urllib.request; json.load(urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3))"

ENTRYPOINT ["kidscontrol-entrypoint"]
