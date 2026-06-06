# NetOps Network Management Console (Feature Spec)

**Date:** 2026-05-10  
**Scope:** Non-crucial side-drawer for managing network definitions — renaming, type assignment, metadata view.  
**Pattern:** Slide-out right panel, inline-edit, autosave. No form-heavy UI.

---

## 1. Background

Current `NetworkPicker` (`Dashboard.tsx` sidebar) shows basic network cards with name, CIDR, description, default toggle, and delete. Rename is not supported. Network "type" (LAN, WiFi, SFP, console, etc.) is not stored anywhere. There is no device count per network.

This feature expands the existing network model to support datacenter-realistic network types and adds a dedicated management console without cluttering the primary topology view.

---

## 2. Database Schema Changes

### `networks` table additions

| Column | Type | Default | Note |
|---|---|---|---|
| `name` | TEXT UNIQUE NOT NULL | — | Already exists |
| `cidr` | TEXT | NULL | Already exists |
| `description` | TEXT | NULL | Already exists |
| `is_default` | INTEGER | 0 | Already exists |
| **`network_type`** | TEXT | NULL | **NEW:** type slug |
| **`tags`** | TEXT | '[]' | **NEW:** JSON string array for free labels |
| **`last_scanned`** | TIMESTAMPTZ | NULL | **NEW:** updated after discovery completes |
| `created` | TIMESTAMPTZ | NOW() | Already exists |
| `updated` | TIMESTAMPTZ | NOW() | Already exists |

### Network Types (enum)

Slug = stored in DB. Label = UI display.

| Slug      | Label            | Description (tooltip)                       |
| --------- | ---------------- | ------------------------------------------- |
| `lan`     | LAN              | Wired local area network segment            |
| `wan`     | WAN              | Wide area or uplink connection              |
| `wifi`    | Wi-Fi            | Wireless LAN / 802.11                       |
| `sfp`     | SFP / Fiber      | Optical fiber via SFP/SFP+/QSFP             |
| `console` | Console / Serial | RS-232 / UART management console port       |
| `bmc`     | BMC / IPMI       | Out-of-band baseboard management controller |
| `mgmt`    | Management       | Out-of-band management network              |
| `dmz`     | DMZ              | Demilitarized zone / perimeter              |
| `vlan`    | VLAN             | Logical virtual LAN segment                 |
| `vpn`     | VPN              | Encrypted tunnel / remote access            |
| `custom`  | Custom           | Manually typed or unclassified              |

---

## 3. API Changes

### `PUT /networks/{network_id}`
Currently supports `name`, `cidr`, `description`, `is_default`. Expand to accept:
- `network_type` (string, enum validation)
- `tags` (string[], max 5, max 20 chars each)

### `GET /networks/{network_id}`
Return enriched payload:
```json
{
  "id": "...",
  "name": "Office Backbone",
  "network_type": "lan",
  "tags": ["production", "rack-3"],
  "cidr": "192.168.10.0/24",
  "description": "Main office VLAN",
  "is_default": false,
  "device_count": 12,
  "last_scanned": "2026-05-10T14:22:00Z",
  "created": "2026-04-20T...",
  "updated": "2026-05-10T..."
}
```

### `GET /networks` (list)
Add aggregated `device_count` to each row via `COUNT(devices.network_id)` JOIN.

---

## 4. UI/UX Design

### Placement
- **Right-side slide-out drawer** (400px wide)
- Triggered by a "Manage" button on Dashboard sidebar or a dedicated icon in the top nav
- Overlay on dark backdrop, does not push main content
- Close via `Escape`, X button, or backdrop click

### Layout (inside drawer)
- Header: "Networks" + device total count + close button
- Each network card:
  ```
  ┌─────────────────────────────────┐
  │ [circle] Production LAN  [x]  │ ← type icon + name + delete
  │ 192.168.1.0/24  ·  12 devices │ ← metadata row
  │ [LAN ▼]  [prod] [rack-3]      │ ← type dropdown + tag chips
  │ last scan: 2h ago              │ ← last_scanned
  └─────────────────────────────────┘
  ```

### Interactions
- **Rename:** Click network name → inline `<input>` with border highlight → `Enter` or blur to save → POST to update API
- **Type select:** Click `LAN ▼` → dropdown of enum options → select → immediate `PUT /networks/{id}` → no save button
- **Tags:** Click chip area → add tag input (inline, 20 char limit) → `Enter` or comma to add → immediate save
- **Delete:** Trash icon hover (red tint) → click → confirm modal → proceed

### Inline-Edit States
- Normal: plain text / styled chips
- Editing: input field, border `[#da1e28] focus:ring-1`, subtle save spinner on `Enter`
- Error: toast (top-right) on API failure, revert to previous value
- Empty after delete: auto-close drawer if last network, or show empty message with "Create first network" CTA

---

## 5. Backend Changes

### `src/storage/database.py`
- Migrate `networks` table: add `network_type TEXT`, `tags TEXT DEFAULT '[]'`, `last_scanned TIMESTAMPTZ`
- SQLite fallback: same columns as TEXT defaults
- Update `list_networks()` to JOIN `devices` for `device_count`
- Update `get_network()` to parse `tags` JSON string into list

### `src/collector/main.py`
- Expand `NetworkUpdate` model: optional `network_type`, `tags`
- Validate `network_type` against enum set
- Update `PUT /networks/{id}` to pass new fields to DB
- After discovery (`POST /discover` or `POST /devices/{id}/poll`), update `networks.last_scanned` for the current network context

### `src/collector/discovery.py`
- Optionally auto-suggest network type during discovery based on CIDR heuristics:
  - `10.x.x.x/24` or `192.168.x.x/24` → suggest `lan`
  - `.1/24`, `.254`, `.1` as first octet in small range → suggest `mgmt` or `lan`
  - Too broad for reliable auto-detect; keep suggestion optional, user overrides

---

## 6. Frontend Changes

### New files
- `web/src/pages/NetworksConsole.tsx` — the drawer component itself
- `web/src/components/NetworkTypeIcon.tsx` — icon mapping for each network type slug
- `web/src/components/InlineEditableField.tsx` — reusable label → input → blur-save
- `web/src/components/TagChips.tsx` — add/remove inline tag chips with autosave
- `web/src/hooks/useNetworkTypes.ts` — enum list for dropdown

### Modified files
- `web/src/pages/Dashboard.tsx`: add "Manage" trigger button next to current `NetworkPicker`
- `web/src/api/endpoints.ts`: add `network_type`, `tags`, `last_scanned` to network payloads
- `web/src/hooks/useNetworks.ts`: add `updateNetwork(payload)` mutation
- `web/src/components/layout/Header.tsx`: optional nav icon for drawer access

---

## 7. Migration Plan

1. **DB migration script** (`scripts/migrate_networks_v2.py` or Alembic rev):
   - `ALTER TABLE networks ADD COLUMN network_type TEXT`
   - `ALTER TABLE networks ADD COLUMN tags TEXT DEFAULT '[]'`
   - `ALTER TABLE networks ADD COLUMN last_scanned TIMESTAMPTZ DEFAULT NULL`
   - Backfill existing rows: `network_type = 'custom'`, `tags = '[]'`

2. **Backend deployment**:
   - Stop poller → run migration → start poller
   - Update `PUT /networks/{id}` validates `network_type` enum

3. **Frontend deployment**:
   - Add drawer component behind feature flag (or deploy with graceful degradation if backend not yet updated)
   - If old backend, `network_type` field ignored but drawer still works for name/description

4. **Rollback**:
   - Drop `network_type`, `tags`, `last_scanned` columns
   - Revert frontend to previous commit

---

## 8. Validation / Test Plan

| Check | Method |
|---|---|
| Inline rename saves | Cypress/Playwright: type, blur, assert `network.name` changed in UI and DB |
| Type select autosaves | Select `sfp` from dropdown → wait 0s → query API → expect type changed |
| Tag max 5 enforced | Add 6th tag → expect UI shows limit message, no API call |
| Device count updates | Add device to network → refresh drawer → count increases |
| Delete last network | Remove last card → drawer shows empty state with "Create" CTA |
| Keyboard shortcuts | Press `Escape` → drawer closes; `Enter` in input triggers save |
| Dark mode | All new cards respect `dark:` classes |

---

## 9. Out of Scope

- Drag-and-drop reordering of networks
- Bulk type assignment (multi-select)
- SVG topology preview inside drawer (keep drawer lightweight)
- Network ACL / firewall rules (stick to metadata only)

---

*Spec written by OpenCode for review. Once approved, next step is DB migration + backend endpoint expansion, then frontend drawer.*
