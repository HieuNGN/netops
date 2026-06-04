#!/bin/bash
set -a
. ./.env
set +a
exec conda run -n netops uvicorn src.collector.main:app --host 127.0.0.1 --port 8000
