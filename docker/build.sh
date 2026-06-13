#!/usr/bin/env bash
set -euo pipefail

# NetOps Docker build helper
# Usage: ./docker/build.sh [dev|prod|clean|logs|stop]

MODE="${1:-dev}"
COMPOSE_FILES="-f docker-compose.yml"

cd "$(dirname "$0")"

case "$MODE" in
  dev)
    echo "Building NetOps (dev)..."
    docker compose $COMPOSE_FILES -f docker-compose.override.yml up -d --build
    echo "Done. Dashboard: http://localhost"
    ;;
  prod)
    echo "Building NetOps (production)..."
    docker compose $COMPOSE_FILES -f docker-compose.prod.yml up -d --build
    echo "Done. Dashboard: http://localhost"
    ;;
  clean)
    echo "Stopping and removing containers, networks, and volumes..."
    docker compose -f docker-compose.yml -f docker-compose.override.yml down -v
    docker compose -f docker-compose.yml -f docker-compose.prod.yml down -v
    echo "Done."
    ;;
  logs)
    docker compose $COMPOSE_FILES logs -f
    ;;
  stop)
    docker compose $COMPOSE_FILES down
    ;;
  *)
    echo "Usage: $0 [dev|prod|clean|logs|stop]"
    exit 1
    ;;
esac
