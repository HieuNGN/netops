# NetOps-Vision

Network topology discovery and monitoring system modeled after CheckCle.

## Features

- **SNMP Discovery**: Automatically discover network devices via SNMP
- **LLDP Topology Mapping**: Build network graphs from LLDP neighbor data
- **Real-time Monitoring**: Periodic polling with configurable intervals (default: 30s)
- **Service Checks**: HTTP, TCP, DNS, Ping, SSL certificate monitoring
- **REST API**: FastAPI backend with SSE streaming for live updates
- **Multi-Channel Alerts**: Webhook, Slack, Telegram, WhatsApp, Email notifications
- **PostgreSQL Persistence**: Async database with connection pooling for scalability

## Quick Start

### 1. Start PostgreSQL

```bash
# Using Docker Compose (recommended)
./scripts/setup_postgres.sh

# Or manually
docker compose -f docker/docker-compose.yml up -d postgres
```

### 2. Install Dependencies

```bash
# Create virtual environment
uv venv
source .venv/bin/activate

# Install dependencies
uv pip install -r requirements.txt
```

### 3. Run Migrations

```bash
python scripts/migrate.py upgrade head
```

### 4. Start the API Server

```bash
uvicorn src.collector.main:app --reload

# Access API docs at http://localhost:8000/docs
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check with poller + alert service stats |
| GET | `/topology` | Current network topology (nodes/links) |
| GET | `/topology/stream` | SSE stream for real-time updates |
| POST | `/topology/refresh` | Trigger immediate poll |
| GET | `/devices` | List all devices |
| POST | `/devices` | Add new device |
| GET | `/devices/{id}` | Get device details |
| PUT | `/devices/{id}` | Update device |
| DELETE | `/devices/{id}` | Delete device |
| POST | `/discover` | Discover devices in network range |
| GET | `/stats` | Poller statistics |
| GET | `/alerts` | List alert configurations |
| POST | `/alerts` | Create alert configuration |
| GET | `/alerts/history` | Recent alert history |
| POST | `/alerts/{id}/test` | Send test alert |
| GET | `/checks` | List all service checks |
| POST | `/checks` | Create a service check |
| GET | `/checks/{id}` | Get service check details |
| PUT | `/checks/{id}` | Update service check |
| DELETE | `/checks/{id}` | Delete service check |
| POST | `/checks/{id}/run` | Run check immediately |
| GET | `/checks/{id}/results` | Get check results history |
| GET | `/checks/stats` | Check scheduler statistics |

## Service Check Types

| Type | Description | Config Fields |
|------|-------------|---------------|
| `http` | HTTP/HTTPS endpoint monitoring | `url`, `method`, `expected_status`, `headers` |
| `tcp` | TCP port connectivity | `host`, `port` |
| `dns` | DNS resolution check | `domain`, `record_type`, `expected_ips` |
| `ping` | ICMP ping check | `host`, `count` |
| `ssl` | SSL certificate expiry | `host`, `port`, `warning_days`, `critical_days` |

## Alert Types

| Type | Description |
|------|-------------|
| `device_down` | Device status changed to offline |
| `device_up` | Device recovered from offline |
| `link_down` | Network link removed |
| `topology_change` | Nodes or links added/removed |
| `check_down` | Service check failed |
| `check_degraded` | Service check degraded (e.g., SSL expiring soon) |

## Notification Channels

| Channel | Config Fields |
|---------|---------------|
| `webhook` | `url`, `method`, `headers`, `payload_template` |
| `slack` | `webhook_url`, `channel`, `username`, `icon_emoji` |
| `telegram` | `bot_token`, `chat_id`, `parse_mode` |
| `whatsapp` | `account_sid`, `auth_token`, `from_number`, `to_number` |
| `email` | `smtp_host`, `smtp_port`, `username`, `password`, `from_email`, `to_emails` |

### Example: Create Telegram Alert

```bash
curl -X POST http://localhost:8000/alerts \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Device Down Alert",
    "alert_type": "device_down",
    "channel": "telegram",
    "config": {
      "bot_token": "YOUR_BOT_TOKEN",
      "chat_id": "YOUR_CHAT_ID"
    }
  }'
```

## CLI Usage

```bash
# SNMP discovery for a single device
python src/collector/spike_snmp.py <host> [-c community] [--action sysdescr|lldp|all]

# Example
python src/collector/spike_snmp.py 192.168.1.1 --action all
```

## Testing

```bash
# Run all tests
./scripts/test.sh

# Run pytest
pytest tests/ -v

# Run specific test file
pytest tests/test_notifications.py -v
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
│   ├── config.py            # Configuration
│   └── checks/              # Service check engine
│       ├── base.py          # Check base classes
│       ├── http_check.py    # HTTP/HTTPS checks
│       ├── tcp_check.py     # TCP port checks
│       ├── dns_check.py     # DNS resolution checks
│       ├── ping_check.py    # ICMP ping checks
│       ├── ssl_check.py     # SSL certificate checks
│       └── scheduler.py     # Check scheduler
├── storage/
│   ├── database.py          # Async PostgreSQL client
│   ├── alembic.ini          # Alembic configuration
│   └── migrations/          # Database migrations
├── api/
│   └── services/
│       ├── alert_service.py # Alert evaluation and dispatch
│       └── notifications/   # Notification channels
│           ├── base.py      # Abstract base class
│           ├── webhook.py   # Generic webhook
│           ├── slack.py     # Slack incoming webhook
│           ├── telegram.py  # Telegram bot API
│           ├── whatsapp.py  # Twilio WhatsApp API
│           └── email.py     # SMTP email
docker/
└── docker-compose.yml       # PostgreSQL container
```

## Roadmap

| Phase | Status | Description |
|-------|--------|-------------|
| Phase 1 | ✅ Complete | Core backend (SNMP polling + API + persistence) |
| Phase 2 | ✅ Complete | Alerting and multi-channel notifications |
| Phase 2.5 | ✅ Complete | PostgreSQL migration |
| Phase 3 | ✅ Complete | Service checks (HTTP, TCP, DNS, Ping, SSL) |
| Phase 4 | ⏳ Pending | React frontend dashboard |
| Phase 5 | ⏳ Pending | Docker deployment |
| Phase 6 | ⏳ Pending | Advanced features (distributed agents, analytics) |

## Project Stats

- **Version:** 0.4.0
- **Lines of Code:** ~4,500
- **Test Coverage:** 19 unit tests (notification channels)
- **Python Version:** 3.11+
