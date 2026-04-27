# NetOps-Vision

Network topology discovery and monitoring system modeled after CheckCle.

## Features

- **SNMP Discovery**: Automatically discover network devices via SNMP
- **LLDP Topology Mapping**: Build network graphs from LLDP neighbor data
- **Real-time Monitoring**: Periodic polling with configurable intervals
- **REST API**: FastAPI backend with SSE streaming for live updates
- **SQLite Persistence**: Embedded database for topology and device storage

## Quick Start

```bash
# Create virtual environment
uv venv
source .venv/bin/activate

# Install dependencies
uv pip install -r requirements.txt

# Start the API server
uvicorn src.collector.main:app --reload

# Access API docs at http://localhost:8000/docs
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check with poller stats |
| GET | `/topology` | Current network topology |
| GET | `/topology/stream` | SSE stream for real-time updates |
| POST | `/topology/refresh` | Trigger immediate poll |
| GET | `/devices` | List all devices |
| POST | `/devices` | Add new device |
| GET | `/devices/{id}` | Get device details |
| PUT | `/devices/{id}` | Update device |
| DELETE | `/devices/{id}` | Delete device |
| POST | `/discover` | Discover devices in network range |
| GET | `/stats` | Poller statistics |
| GET | `/alerts` | List alert configs |
| POST | `/alerts` | Create alert config |

## CLI Usage

```bash
# SNMP discovery for a single device
python src/collector/spike_snmp.py <host> [-c community] [--action sysdescr|lldp|all]

# Example
python src/collector/spike_snmp.py 192.168.1.1 --action all
```

## Architecture

```
src/
├── collector/
│   ├── main.py              # FastAPI application
│   ├── snmp_poller.py       # Periodic polling orchestrator
│   ├── spike_snmp.py        # Low-level SNMP queries
│   ├── topology_builder.py  # Network graph construction
│   ├── discovery.py         # Network range scanner
│   └── config.py            # Configuration
├── pb/
│   └── client.py            # SQLite persistence layer
```

## Roadmap

- [x] Phase 1: Core backend service (SNMP polling + API)
- [ ] Phase 2: Alerting and notifications (webhook, email, Slack)
- [ ] Phase 3: React frontend dashboard
- [ ] Phase 4: Docker deployment
- [ ] Phase 5: Advanced features (distributed agents, analytics)
