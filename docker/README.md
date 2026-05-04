# NetOps-Vision Docker Deployment

Production-ready containerized deployment for NetOps-Vision network monitoring system.

## Quick Start

```bash
# Build and start all services
cd docker
docker-compose up -d --build

# Check service status
docker-compose ps

# View logs
docker-compose logs -f backend
docker-compose logs -f frontend

# Stop all services
docker-compose down
```

## Services

| Service | Port | Description |
|---------|------|-------------|
| Frontend | http://localhost:80 | React dashboard (Nginx) |
| Backend | http://localhost:8000 | FastAPI API server |
| PostgreSQL | localhost:5432 | Primary database |

## Configuration

### Environment Variables

**Backend:**
- `DB_HOST` - PostgreSQL host (default: `postgres`)
- `DB_PORT` - PostgreSQL port (default: `5432`)
- `DB_NAME` - Database name (default: `netops`)
- `DB_USER` - Database user (default: `netops`)
- `DB_PASSWORD` - Database password (default: `netops`)
- `SNMP_HOST` - Default SNMP target host
- `SNMP_COMMUNITY` - Default SNMP community string
- `SNMP_TIMEOUT` - SNMP query timeout in seconds
- `SNMP_RETRIES` - SNMP retry count
- `LOG_LEVEL` - Logging verbosity (DEBUG, INFO, WARNING, ERROR)

### SNMP Network Access

For SNMP polling to work, the container needs network access to your devices:

```yaml
# Option 1: Host networking (simplest, gives container full host network access)
network_mode: "host"

# Option 2: Custom network with device access
# Add to backend service:
extra_hosts:
  - "router1:192.168.1.1"
  - "switch1:192.168.1.10"
```

## Data Persistence

- PostgreSQL data: `postgres_data` volume
- SQLite fallback data: `backend_data` volume

## Health Checks

All services have health checks configured:

```bash
# Check health status
curl http://localhost:8000/health
curl http://localhost:80/health
```

## Development Mode

For development with hot-reload:

```bash
# Backend (from project root)
uvicorn src.collector.main:app --reload --host 0.0.0.0 --port 8000

# Frontend (from web directory)
npm run dev
```

## Production Notes

1. **Change default credentials** - Update POSTGRES_PASSWORD in docker-compose.yml
2. **Use external network** - Configure SNMP_HOST to reach your network devices
3. **Enable SSL** - Add a reverse proxy (Traefik, Caddy) for HTTPS
4. **Backup volumes** - Regularly backup postgres_data volume

## Troubleshooting

**Backend won't start:**
```bash
docker-compose logs backend
# Check database connection
docker-compose exec backend python -c "from src.storage.database import AsyncPostgresClient; import asyncio; asyncio.run(AsyncPostgresClient().connect())"
```

**Frontend shows "Disconnected":**
```bash
# Verify backend is accessible
docker-compose exec frontend wget -qO- http://backend:8000/health
```

**SNMP polling fails:**
- Ensure devices are reachable from the backend container
- Check SNMP community string matches device configuration
- Verify firewall allows UDP 161 traffic
