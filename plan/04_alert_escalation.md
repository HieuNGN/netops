# Feature 4: Alert Severity Escalation

## Problem Statement

Alerts fire at a fixed severity and stay there until resolved. No progression from warning → critical after a timeout. This is basic ITIL incident management — PRTG has escalation chains, SolarWinds has AlertStack with AIOps escalation, Datadog has monitor priority escalation.

**Impact on presentation:** "What happens if an alert is ignored?" → Nothing. It just stays at the same severity. Not how real monitoring tools work.

---

## Current State

### Backend
- `alert_service.py` — alerts fire at fixed severity (`critical`, `warning`, `info`)
- `alert_configs` table: `id, name, alert_type, channel, config_json, integration_id, enabled, created`
- No escalation fields in schema
- `_active_alerts` dict tracks firing alerts with `fired_at` timestamp
- No periodic check for escalation timeouts
- Severity hardcoded per alert type:
  - `device_down` → `critical`
  - `device_up` → `info`
  - `check_down` → `critical`
  - `check_degraded` → `warning`
  - `topology_change` → `warning` or `info`
  - `link_down` → `warning`

### Frontend
- `Alerts.tsx` — alert rule editor has no escalation config
- Active alerts show severity badge (no escalation indicator)
- No "escalated" state in UI

---

## Target State

### Escalation Model
```
Alert fires at initial_severity (e.g., "warning")
         │
         ▼
   ┌─────────────┐
   │  Wait N min  │ ← escalation_minutes (configurable per rule)
   └──────┬──────┘
          │
          ▼ (if still firing and not acknowledged)
   Escalate to escalated_severity (e.g., "critical")
          │
          ▼
   Re-send notification at new severity
```

### Configuration (Per Alert Rule)
```json
{
  "name": "Device Down → Slack",
  "alert_type": "device_down",
  "channel": "slack",
  "config": { "webhook_url": "..." },
  "escalation_minutes": 5,
  "escalated_severity": "critical"
}
```

- `escalation_minutes`: null = no escalation (default), 5 = escalate after 5 min
- `escalated_severity`: target severity after escalation (default: "critical")
- Escalation only fires if alert is still `firing` (not `acknowledged` or `resolved`)
- Re-sends notification at new severity level

### User Flow
1. Admin creates alert rule: "If device_down → Slack at warning"
2. Sets escalation: "After 5 minutes → escalate to critical"
3. Device goes offline → Slack notification: "⚠️ WARNING: Device offline"
4. 5 minutes pass, no one acknowledges
5. Slack notification: "🔴 CRITICAL: Device offline (escalated after 5m)"
6. Admin acknowledges → escalation timer stops
7. Device recovers → alert resolved

---

## Implementation Plan

### Step 1: Database Migration

**File:** `src/storage/migrations/versions/022_alert_escalation.py` (NEW)

```python
"""Add escalation fields to alert_configs.

Revision ID: 022
Revises: 021
Create Date: 2025-01-15

Adds:
  - escalation_minutes: int, nullable (null = no escalation)
  - escalated_severity: string, nullable (default 'critical')
"""

from alembic import op
import sqlalchemy as sa

revision = '022'
down_revision = '021'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('alert_configs', sa.Column('escalation_minutes', sa.Integer(), nullable=True))
    op.add_column('alert_configs', sa.Column('escalated_severity', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('alert_configs', 'escalated_severity')
    op.drop_column('alert_configs', 'escalation_minutes')
```

### Step 2: Update Table Definition

**File:** `src/storage/database.py`

Add columns to `alert_configs_table`:
```python
alert_configs_table = Table(
    "alert_configs",
    Base.metadata,
    Column("id", String, primary_key=True),
    Column("name", String, nullable=False),
    Column("alert_type", String, nullable=False),
    Column("channel", String, nullable=False),
    Column("config_json", String),
    Column("integration_id", String),
    Column("enabled", Integer, default=1),
    Column("escalation_minutes", Integer, nullable=True),  # NEW
    Column("escalated_severity", String, nullable=True),   # NEW
    Column("created", DateTime, server_default=func.now()),
    Index("idx_alert_configs_enabled", "enabled"),
    Index("idx_alert_configs_integration", "integration_id"),
)
```

### Step 3: SQLite Mirror

**File:** `src/storage/sqlite_client.py`

Add migration logic in `_ensure_schema()`:
```python
# Check if escalation columns exist
cursor = await self._db.execute("PRAGMA table_info(alert_configs)")
columns = {row[1] for row in cursor.fetchall()}

if 'escalation_minutes' not in columns:
    await self._db.execute("ALTER TABLE alert_configs ADD COLUMN escalation_minutes INTEGER")
if 'escalated_severity' not in columns:
    await self._db.execute("ALTER TABLE alert_configs ADD COLUMN escalated_severity TEXT")
```

### Step 4: Update Pydantic Models

**File:** `src/collector/main.py`

Update `AlertConfigCreate` model:
```python
class AlertConfigCreate(BaseModel):
    name: str
    alert_type: str
    channel: str
    config: dict[str, Any] = {}
    integration_id: Optional[str] = None
    enabled: bool = True
    escalation_minutes: Optional[int] = Field(
        None, 
        description="Minutes before escalation. null = no escalation.",
        ge=1, le=1440  # 1 min to 24 hours
    )
    escalated_severity: Optional[str] = Field(
        "critical",
        description="Severity after escalation. Default: critical"
    )
```

Update `AlertConfigUpdate` model:
```python
class AlertConfigUpdate(BaseModel):
    name: Optional[str] = None
    config: Optional[dict[str, Any]] = None
    integration_id: Optional[str] = None
    enabled: Optional[bool] = None
    escalation_minutes: Optional[int] = None
    escalated_severity: Optional[str] = None
```

### Step 5: Update DB Methods

**File:** `src/storage/database.py`

Update `create_alert_config` and `update_alert_config` to handle new fields:
```python
async def create_alert_config(self, data: dict[str, Any]) -> dict[str, Any]:
    config_id = str(uuid.uuid4())
    async with self._get_connection() as conn:
        await conn.execute(
            """
            INSERT INTO alert_configs 
            (id, name, alert_type, channel, config_json, integration_id, enabled, 
             escalation_minutes, escalated_severity)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            """,
            config_id,
            data["name"],
            data["alert_type"],
            data["channel"],
            json.dumps(data.get("config", {})),
            data.get("integration_id"),
            1 if data.get("enabled", True) else 0,
            data.get("escalation_minutes"),
            data.get("escalated_severity", "critical"),
        )
    return {"id": config_id, **data}
```

### Step 6: Implement Escalation Logic

**File:** `src/api/services/alert_service.py`

Add escalation check method:
```python
async def check_escalations(self) -> int:
    """Check all firing alerts for escalation timeouts.
    
    Returns number of alerts escalated.
    Called periodically by poller loop (every 60s).
    """
    import time
    now = time.time()
    escalated_count = 0
    
    # Get all alert configs with escalation enabled
    configs = await self.db_client.list_alert_configs()
    escalation_configs = {
        cfg["alert_type"]: cfg
        for cfg in configs
        if cfg.get("escalation_minutes") and cfg.get("enabled", True)
    }
    
    for key, alert in list(self._active_alerts.items()):
        # Skip if already escalated or acknowledged
        if alert.get("escalated") or alert["status"] != "firing":
            continue
        
        alert_type = alert["alert_type"]
        cfg = escalation_configs.get(alert_type)
        if not cfg:
            continue
        
        escalation_minutes = cfg.get("escalation_minutes")
        if not escalation_minutes:
            continue
        
        fired_at = alert.get("fired_at", 0)
        elapsed_minutes = (now - fired_at) / 60
        
        if elapsed_minutes >= escalation_minutes:
            # Escalate!
            new_severity = cfg.get("escalated_severity", "critical")
            old_severity = alert["severity"]
            
            alert["escalated"] = True
            alert["severity"] = new_severity
            alert["escalated_at"] = now
            
            escalated_count += 1
            
            # Re-send notification at new severity
            channel = await self.get_notification_channel(
                cfg.get("channel", "webhook"),
                cfg.get("config_json", {}),
                integration_id=cfg.get("integration_id"),
            )
            
            if channel:
                message = NotificationMessage(
                    title=f"🔴 ESCALATED: {alert['title']}",
                    message=f"{alert['message']}\n\nEscalated from {old_severity} to {new_severity} after {escalation_minutes} minutes",
                    severity=new_severity,
                    alert_type=alert_type,
                    metadata=alert,
                )
                
                try:
                    if cfg.get("channel", "").lower() == "email":
                        channel.send(message)
                    else:
                        await channel.send(message)
                except Exception:
                    pass  # Don't fail on notification error
    
    return escalated_count
```

### Step 7: Call Escalation Check in Poller Loop

**File:** `src/collector/snmp_poller.py`

Add escalation check to poll loop (after topology poll):
```python
# In _poll_loop method, after topology poll:
if hasattr(self, 'alert_service') and self.alert_service:
    try:
        escalated = await self.alert_service.check_escalations()
        if escalated > 0:
            logger.info(f"Escalated {escalated} alerts")
    except Exception as e:
        logger.error(f"Escalation check failed: {e}")
```

### Step 8: Frontend — Escalation Config UI

**File:** `web/src/pages/Alerts.tsx`

Add escalation fields to alert rule editor form:
```typescript
<div className="space-y-2">
  <label className="block text-sm font-medium text-foreground">
    Escalation (optional)
  </label>
  <div className="flex items-center gap-2">
    <span className="text-sm text-muted-foreground">After</span>
    <input
      type="number"
      value={escalationMinutes || ''}
      onChange={(e) => setEscalationMinutes(e.target.value ? parseInt(e.target.value) : null)}
      placeholder="—"
      min={1}
      max={1440}
      className="w-20 px-2 py-1 text-sm border border-input bg-card text-foreground rounded-sm"
    />
    <span className="text-sm text-muted-foreground">minutes, escalate to</span>
    <select
      value={escalatedSeverity}
      onChange={(e) => setEscalatedSeverity(e.target.value)}
      className="px-2 py-1 text-sm border border-input bg-card text-foreground rounded-sm"
    >
      <option value="critical">critical</option>
      <option value="warning">warning</option>
      <option value="info">info</option>
    </select>
  </div>
  <p className="text-xs text-muted-foreground">
    Leave blank to disable escalation. Alert must be unacknowledged to escalate.
  </p>
</div>
```

### Step 9: Frontend — Show Escalated State

**File:** `web/src/pages/Alerts.tsx`

In active alerts list, show escalation indicator:
```typescript
{alert.escalated && (
  <span className="inline-flex items-center gap-1 px-1.5 py-0.5 text-[10px] uppercase tracking-wide rounded-sm bg-thinkpad-red/10 text-thinkpad-red font-medium">
    escalated
  </span>
)}
```

### Step 10: Update API Types

**File:** `web/src/api/endpoints.ts`

Update `AlertConfig` interface:
```typescript
export interface AlertConfig {
  id: string;
  name: string;
  alert_type: string;
  channel: string;
  config_json: Record<string, any>;
  integration_id: string | null;
  enabled: boolean;
  escalation_minutes: number | null;  // NEW
  escalated_severity: string | null;  // NEW
  created: string;
}
```

Update `ActiveAlert` interface:
```typescript
export interface ActiveAlert {
  key: string;
  alert_type: string;
  target_id: string;
  severity: string;
  title: string;
  message: string;
  status: 'firing' | 'acknowledged';
  fired_at: number;
  escalated?: boolean;        // NEW
  escalated_at?: number;      // NEW
}
```

---

## Database Changes

**Migration 022:** Add `escalation_minutes` (int, nullable) and `escalated_severity` (string, nullable) to `alert_configs`.

**Reversible:** Yes — `downgrade()` drops both columns.

---

## Testing

### Backend Tests
```python
# tests/test_alert_escalation.py
async def test_escalation_fires_after_timeout():
    """Alert escalates from warning to critical after N minutes."""

async def test_escalation_skips_acknowledged():
    """Acknowledged alerts don't escalate."""

async def test_escalation_disabled_by_default():
    """Alerts without escalation_minutes don't escalate."""

async def test_escalation_resends_notification():
    """Escalation triggers new notification at new severity."""
```

### Manual Testing
1. Create alert rule with escalation: 1 min → critical
2. Trigger alert (device goes offline)
3. Wait 1 minute → second notification arrives with "ESCALATED" prefix
4. Acknowledge alert → escalation stops
5. Create rule without escalation → no second notification

---

## Estimated Effort

| Task | Hours |
|------|-------|
| Database migration (PG + SQLite) | 1h |
| Update table definitions + Pydantic models | 1h |
| Update DB CRUD methods | 1h |
| Implement `check_escalations` logic | 3h |
| Wire into poller loop | 0.5h |
| Backend tests | 2h |
| Frontend: escalation config UI | 2h |
| Frontend: escalated state indicator | 1h |
| Frontend: API type updates | 0.5h |
| Manual testing | 1h |
| **Total** | **13h** |

---

## Notes

- **Escalation is opt-in** — `escalation_minutes = null` means no escalation (backward compatible)
- **Re-notification is critical** — escalation must send a new notification, not just change severity
- **Acknowledged alerts don't escalate** — respects operator action
- **Poller loop integration** — check every 60s (matches poll interval)
- **No UI for escalation history** — future enhancement (show "escalated at" timestamp)
