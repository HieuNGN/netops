# NetOps-Vision

Network topology discovery and monitoring system modeled after CheckCle.

## Features

- **SNMP Discovery**: Automatically discover network devices via SNMP
- **LLDP Topology Mapping**: Build network graphs from LLDP neighbor data
- **Real-time Monitoring**: Periodic polling with configurable intervals (default: 30s)
- **REST API**: FastAPI backend with SSE streaming for live updates
- **Multi-Channel Alerts**: Webhook, Slack, Telegram, WhatsApp, Email notifications
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

## Alert Types

| Type | Description |
|------|-------------|
| `device_down` | Device status changed to offline |
| `device_up` | Device recovered from offline |
| `link_down` | Network link removed |
| `topology_change` | Nodes or links added/removed |

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
│   └── config.py            # Configuration
├── pb/
│   └── client.py            # SQLite persistence layer
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
```

## Roadmap

| Phase | Status | Description |
|-------|--------|-------------|
| Phase 1 | ✅ Complete | Core backend (SNMP polling + API + persistence) |
| Phase 2 | ✅ Complete | Alerting and multi-channel notifications |
| Phase 3 | ⏳ Pending | React frontend dashboard |
| Phase 4 | ⏳ Pending | Docker deployment |
| Phase 5 | ⏳ Pending | Advanced features (distributed agents, analytics) |

## Project Stats

- **Version:** 0.2.0
- **Lines of Code:** ~2,500
- **Test Coverage:** 19 unit tests (notification channels)
- **Python Version:** 3.11+
