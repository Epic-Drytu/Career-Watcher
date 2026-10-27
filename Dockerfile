FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# pdftotext enables local scoring for PDF resumes. DOCX parsing uses Python's
# standard library. No app or resume contents are copied into the image.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates poppler-utils \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --uid 10001 --create-home careerwatcher \
    && mkdir -p /data \
    && chown careerwatcher:careerwatcher /data

WORKDIR /app
COPY --chown=careerwatcher:careerwatcher jobwatcher/ ./jobwatcher/

USER 10001:10001
VOLUME ["/data"]
EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/', timeout=2)" || exit 1

# Interactive launches ask before starting. Detached/non-interactive launches
# start directly; bind the app inside the container and publish to host loopback.
CMD ["sh", "-c", "if [ -t 0 ]; then printf '\\nStart Career Watcher now? [Y/n] '; read answer; case \"$answer\" in n|N|no|NO) echo 'Not started.'; exit 0;; esac; fi; exec python3 -m jobwatcher.app ui --host 0.0.0.0 --display-host 127.0.0.1 --port 8765 --data /data --interval-seconds 21600 --no-browser"]
