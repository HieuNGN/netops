# NetOps Deployment Review — 2026-05-14

## Blockers

1. **Dependency gap**: `python-jose[cryptography]>=3.3.0` missing from `requirements.txt`. Docker build crash on auth import.
2. **nginx.conf no `/api`**: auth + config endpoints 404 in production.
3. **JWT secret hardcoded**: same secret across every deploy. Risk.
4. **VITE_API_URL hardcode**: frontend pins `localhost:8000`. Breaks on domain.

## Hosting Feasibility

| Platform | Fit | Why |
|----------|-----|-----|
| VPS / Docker Compose | Best | One command, persistent SQLite/PSQL, full control |
| Self-host / RPi | Good | SQLite ok, ARM needs `libsnmp-dev` |
| Railway / Fly.io | OK | Auto-deploy, but must use PSQL (no persistent disk) |
| Vercel + Render split | Poor | SSE max 10s on Vercel → kill stream. Need WebSocket fallback |
| Fusion CP / Cloudflare | Weak | PocketBase script orphaned. FastAPI mismatch |

## Required Fixes

1. Add `python-jose` to `requirements.txt`.
2. Add `location /api` proxy block to `nginx.conf`.
3. Make `JWT_SECRET` fail-fast — no fallback hardcode, exit if env missing.
4. Remove `VITE_API_URL` from builds. Use relative `'/api'`. Nginx proxy handles the rest.
5. Add `SERVER_NAME` / `BASE_URL` env for absolute links in alerts.
6. Docker build needs `VITE_API_URL=` (empty = relative). Or remove env check entirely.

## Open Questions
- Target: home self-host or public VPS?
- Domain + SSL (Let's Encrypt)?
- Keep React SPA or lighter stack?
- SSE → short-poll fallback for cloud deploy?

## Required OpenCode APIs / Tools / Resources

- Cloudflare Pages CLI / GitHub Pages for static frontend.
- Docker Compose deploy guide: Traefik reverse proxy + Let's Encrypt auto-cert.
- `uvicorn` production run command: `uvicorn src.collector.main:app --host 0.0.0.0 --port 8000 --workers 2`.
- `gunicorn + uvicorn.workers.UvicornWorker` if Gunicorn preferred over Uvicorn multi-process.

## Priority: Now
- Fix requirements + nginx + JWT → all blockers.
- Then pick target stack (VPS vs PaaS).
- Write deploy docs matching choice.
