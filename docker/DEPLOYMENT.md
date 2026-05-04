# NetOps-Vision Deployment Guide

## Production Deployment with Docker

### Prerequisites

- Docker Desktop or Docker Engine 20+
- Docker Compose v2+
- Network access to SNMP devices (UDP 161)

### Quick Start

```bash
cd docker

# Start all services
docker compose up -d --build

# Verify services are running
docker compose ps

# Access the application
# Frontend: http://localhost:80
# Backend API: http://localhost:8000
# API Health: http://localhost:8000/health
```

### Stopping Services

```bash
# Stop all services
docker compose down

# Stop and remove volumes (deletes all data)
docker compose down -v
```

### Viewing Logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f backend
docker compose logs -f frontend
docker compose logs -f postgres
```

## Configuration

### Environment Variables

Create a `.env` file in the `docker/` directory:

```bash
# PostgreSQL
POSTGRES_DB=netops
POSTGRES_USER=netops
POSTGRES_PASSWORD=your-secure-password

# Backend
LOG_LEVEL=INFO
SNMP_TIMEOUT=3
SNMP_RETRIES=2

# Network (adjust for your environment)
SNMP_HOST=192.168.1.1
```

### SNMP Network Access

For SNMP polling to reach your network devices, you have several options:

#### Option 1: Host Network Mode (Simplest)

Add to `backend` service in `docker-compose.yml`:

```yaml
services:
  backend:
    network_mode: "host"
```

**Pros**: Full network access, no configuration needed
**Cons**: Less isolation, only one service can use host network

#### Option 2: Static Routes

If your devices are on a specific subnet:

```yaml
services:
  backend:
    extra_hosts:
      - "router1:192.168.1.1"
      - "switch1:192.168.1.10"
```

#### Option 3: Bridge with Custom Network

For Docker Desktop, ensure your network is routable from containers.

## Backup and Restore

### Backup Database

```bash
# PostgreSQL backup
docker exec netops-postgres pg_dump -U netops netops > backup.sql

# SQLite backup (if using fallback)
docker cp netops-backend:/app/data/netops.db backup.db
```

### Restore Database

```bash
# PostgreSQL restore
cat backup.sql | docker exec -i netops-postgres psql -U netops -d netops

# SQLite restore
docker cp backup.db netops-backend:/app/data/netops.db
```

## Scaling and Performance

### Resource Limits

Add to services in `docker-compose.yml`:

```yaml
services:
  backend:
    deploy:
      resources:
        limits:
          cpus: '1.0'
          memory: 1G
        reservations:
          cpus: '0.5'
          memory: 512M
  
  postgres:
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 2G
```

### PostgreSQL Tuning

For production, consider:

```yaml
postgres:
  command: >
    postgres
    -c max_connections=100
    -c shared_buffers=512MB
    -c effective_cache_size=1GB
    -c work_mem=16MB
```

## Monitoring

### Health Checks

```bash
# Backend health
curl http://localhost:8000/health

# Frontend health  
curl http://localhost:80/

# Database health
docker exec netops-postgres pg_isready -U netops
```

### Prometheus Metrics (Future)

The backend can expose metrics at `/metrics` endpoint for Prometheus scraping.

## Troubleshooting

### Backend won't connect to database

```bash
# Check database is healthy
docker compose ps postgres

# Check backend logs
docker compose logs backend

# Test connection from backend container
docker exec netops-backend python -c "
import asyncio
from src.storage.database import AsyncPostgresClient
async def test():
    client = AsyncPostgresClient()
    await client.connect()
    print('Connected!')
    await client.close()
asyncio.run(test())
"
```

### Frontend shows "Disconnected"

1. Verify backend is running: `docker compose ps backend`
2. Check network connectivity: `docker exec netops-frontend wget -qO- http://backend:8000/health`
3. Review nginx config: `docker exec netops-frontend cat /etc/nginx/conf.d/default.conf`

### SNMP polling fails

1. Check network reachability from container
2. Verify SNMP community string
3. Test SNMP manually:
   ```bash
   docker exec netops-backend snmpwalk -v2c -c public 192.168.1.1 sysDescr
   ```

## Production Checklist

- [ ] Change default PostgreSQL password
- [ ] Configure SSL/TLS termination (add reverse proxy)
- [ ] Set up log aggregation (ELK, Loki, etc.)
- [ ] Configure backup strategy
- [ ] Set up monitoring and alerting
- [ ] Test SNMP connectivity to all devices
- [ ] Document network topology and device IPs
- [ ] Configure firewall rules for container network

## Development Mode

For development with hot-reload:

```bash
# Backend (project root)
source .venv/bin/activate
uvicorn src.collector.main:app --reload --host 0.0.0.0 --port 8000

# Frontend (web directory)
cd web
npm run dev
```

The Docker setup is intended for production deployments where you want consistent, isolated services.
