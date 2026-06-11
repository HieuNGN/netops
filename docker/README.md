# NetOps Docker Setup

## Quick Start

```bash
cd docker
cp .env.example .env
# Edit .env — set strong JWT_SECRET and POSTGRES_PASSWORD
JWT_SECRET=dev docker compose up -d --build
```

- Frontend → http://localhost
- API docs → http://localhost:8000/docs
- Prometheus metrics → http://localhost:8000/metrics

## Files

| File | Purpose |
|------|---------|
| `docker-compose.yml` | **Production** compose (read-only, internal PG, restart always) |
| `docker-compose.override.yml` | **Development** overrides (exposed PG port, source mounts, DEBUG log) |
| `docker-compose.prod.yml` | Backward-compat placeholder (production is now the default) |
| `Dockerfile.backend` | Python 3.11-slim + FastAPI image |
| `Dockerfile.frontend` | Multi-stage Node 20 → Nginx Alpine React SPA image |
| `nginx.conf` | Reverse proxy + SSE + SPA fallback |
| `.env.example` | Docker-specific environment variable template |

## Development

```bash
cd docker
# Override is auto-picked up:
JWT_SECRET=dev docker compose up -d --build
# Source mounted at /app/src, /app/scripts for live changes
```

## Production

```bash
cd docker
cp .env.example .env
# Edit .env with real credentials
docker compose up -d --build
```

Production defaults:
- PostgreSQL not exposed to host (internal network: `172.28.0.0/16`)
- Backend + frontend root filesystems read-only with tmpfs for writable dirs
- `restart: always` on all services
- Health checks enforce startup order

## Configuration

Required environment variables (set in `.env` or shell):

| Var | Required | Default |
|-----|----------|---------|
| `JWT_SECRET` | **Yes** | — (fail-fast) |
| `POSTGRES_PASSWORD` | **Yes** | `netops` |
| `NETOPS_ENCRYPTION_KEY` | No | — (passthrough) |
| `NETOPS_COOKIE_SECURE` | No | `0` (set `1` for HTTPS) |
| `VITE_API_URL` | No | `/api` |
| `FRONTEND_PORT` | No | `80` |
| `BACKEND_PORT` | No | `8000` |
| `SNMP_COMMUNITY` | No | `public` |

Generate a Fernet encryption key:
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## Health Checks

All services have Docker health checks:
- **postgres** — `pg_isready`
- **backend** — HTTP `GET /health`
- **frontend** — HTTP `GET /` via curl

## Networks & Volumes

- **Network** `netops-network` (bridge, `172.28.0.0/16`)
- **Volume** `postgres_data` — persistent PostgreSQL data
- **Volume** `backend_data` — persistent app data (SQLite fallback, runtime files)
