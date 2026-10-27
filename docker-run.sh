#!/bin/sh
set -eu
cd "$(dirname "$0")"

docker build -t career-watcher:local .
docker volume create career-watcher-data >/dev/null
exec docker run --rm -it \
  --publish 127.0.0.1:8765:8765 \
  --volume career-watcher-data:/data \
  career-watcher:local
