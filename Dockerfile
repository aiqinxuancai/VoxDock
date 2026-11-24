# syntax=docker/dockerfile:1

# Static ffmpeg build (multi-arch), used to convert uploaded reference audio when a platform
# does not accept the original container (e.g. m4a/webm/flac -> wav).
FROM mwader/static-ffmpeg:9.1 AS ffmpeg

FROM python:3.12-slim

ARG VERSION=dev
LABEL org.opencontainers.image.title="VoxDock" \
      org.opencontainers.image.description="多平台声音克隆聚合服务：火山引擎 / 阿里云百炼（CosyVoice·千问）/ MiniMax / 智谱" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.version="${VERSION}"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=Asia/Shanghai \
    VOXDOCK_DATA_DIR=/data \
    VOXDOCK_VERSION=${VERSION}

COPY --from=ffmpeg /ffmpeg /usr/local/bin/ffmpeg

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app

VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4)" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
