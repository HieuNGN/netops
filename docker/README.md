# NetOps Docker Setup

## Quick Start

```bash
cd docker
docker compose up -d --build
```

- Frontend → http://localhost
- API docs → http://localhost:8000/docs
- Prometheus metrics → http://localhost:8000/metrics

## Files

| File | Purpose |
|------|---------|
| `docker-compose.yml` | Base production-ready services (postgres, backend, frontend) |
| `docker-compose.override.yml` | Development overrides (mounts source code, debug logging) |
| `docker-compose.prod.yml` | Production hardening (no exposed DB port, read-only containers) |
| `Dockerfile.backend` | Python 3.11 + FastAPI image |
| `Dockerfile.frontend` | Multi-stage Node → Nginx React SPA image |
| `nginx.conf` | Reverse proxy + SSE + SPA fallback |
| `.env.example` | Docker-specific environment variables |

## Development

The `docker-compose.override.yml` is picked up automatically when running from the `docker/` directory:

```bash
cd docker
docker compose up -d --build
```

To see the merged config:

```bash
docker compose config
```

## Production

```bash
cd docker
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

Override ports or secrets via an `.env` file:

```bash
cp .env.example .env
# edit .env
docker compose --env-file .env up -d
```

## Health Checks

All services have Docker health checks:
- **postgres** — `pg_isready`
- **backend** — HTTP `/health`
- **frontend** — HTTP `/` via curl

## Networks & Volumes

- **Network** `netops-network` (bridge, `172.28.0.0/16`)
- **Volume** `postgres_data` — persistent PostgreSQL data
- **Volume** `backend_data` — persistent SQLite fallback / app data
