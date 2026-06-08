# Feature 3: CSV Export for Devices

## Problem Statement

No way to export device data from NetOps. Professors and managers expect "Export Report" buttons. PRTG has CSV/PDF export, SolarWinds has report builder, Datadog has notebook export. Even a simple CSV export adds significant perceived value.

**Impact on presentation:** "Can you export this data?" → No. Missed opportunity to show practical utility.

---

## Current State

### Frontend
- `Devices.tsx` has Import button (JSON/CSV) but no Export button
- Device data available in `devices` array from `useDevices()` hook
- Filtered devices already computed (`filteredDevices`) — respects search + filters
- No export functionality anywhere in the app

### Data Available
```typescript
interface Device {
  id: string;
  name: string;
  ip_address: string;
  community: string;
  status: 'online' | 'offline' | 'unknown' | 'discovered';
  sys_descr: string;
  discovery_method: string;
  last_polled: string;
  created: string;
  updated: string;
  network_id?: string;
  snmp_version: string;
  snmpv3_username: string | null;
  // ... other fields
}
```

---

## Target State

### User Flow
1. User on `/devices` page
2. Applies filters (optional): search, status, network, tag
3. Clicks "Export CSV" button
4. Browser downloads `netops-devices-2025-01-15.csv`
5. CSV contains all filtered devices with key fields

### CSV Format
```csv
name,ip_address,status,sys_descr,discovery_method,network,last_polled,snmp_version
Router-1,192.168.1.1,online,Cisco IOS 15.1,snmp,LAN,2025-01-15 12:34:56,2c
Switch-2,192.168.1.2,offline,,ping,LAN,2025-01-15 12:30:00,2c
Firewall-1,192.168.1.254,online,PAN-OS 10.2,manual,DMZ,2025-01-15 12:35:00,3
```

### Export Options
- **Export filtered:** Only devices matching current filters (default)
- **Export all:** All devices regardless of filters (future enhancement)
- **Filename:** `netops-devices-{YYYY-MM-DD}.csv`

---

## Implementation Plan

### Approach: Client-Side CSV Generation

**Why client-side?**
- Data already in browser (no API call needed)
- Instant download (no server processing)
- Respects current filters (export what you see)
- No backend changes required

### Step 1: Add Export Button to Devices Page

**File:** `web/src/pages/Devices.tsx`

Add import:
```typescript
import { Download } from 'lucide-react';
```

Add export function:
```typescript
const exportToCSV = () => {
  // Define columns to export
  const headers = [
    'name',
    'ip_address',
    'status',
    'sys_descr',
    'discovery_method',
    'network',
    'last_polled',
    'snmp_version',
  ];

  // Map devices to rows
  const rows = filteredDevices.map((device) => {
    const network = networks.find((n) => n.id === device.network_id);
    return [
      device.name || '',
      device.ip_address,
      device.status,
      device.sys_descr || '',
      device.discovery_method || '',
      network?.name || '',
      device.last_polled ? new Date(device.last_polled).toISOString().replace('T', ' ').slice(0, 19) : '',
      device.snmp_version || '2c',
    ];
  });

  // Convert to CSV string
  const csvContent = [
    headers.join(','),
    ...rows.map((row) =>
      row
        .map((cell) => {
          // Escape quotes and wrap in quotes if contains comma/quote/newline
          const str = String(cell);
          if (str.includes(',') || str.includes('"') || str.includes('\n')) {
            return `"${str.replace(/"/g, '""')}"`;
          }
          return str;
        })
        .join(',')
    ),
  ].join('\n');

  // Create download link
  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
  const link = document.createElement('a');
  const url = URL.createObjectURL(blob);
  const date = new Date().toISOString().slice(0, 10);
  
  link.setAttribute('href', url);
  link.setAttribute('download', `netops-devices-${date}.csv`);
  link.style.visibility = 'hidden';
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);

  toast.success('Export complete', `${filteredDevices.length} devices exported`);
};
```

### Step 2: Add Export Button to UI

**File:** `web/src/pages/Devices.tsx`

Add button next to Import button:
```typescript
<button
  onClick={exportToCSV}
  disabled={filteredDevices.length === 0}
  className="inline-flex items-center gap-1.5 text-sm px-3 py-1.5 bg-slate-600 text-white rounded-sm hover:bg-slate-700 disabled:opacity-50 disabled:cursor-not-allowed"
  title={filteredDevices.length === 0 ? 'No devices to export' : 'Export filtered devices to CSV'}
>
  <Download className="h-3.5 w-3.5" />
  <span>Export CSV{hasFilters ? ` (${filteredDevices.length})` : ''}</span>
</button>
```

Position in button group (after Import, before Scan):
```typescript
<div className="flex flex-wrap gap-2">
  <button ...>Reset & Rescan</button>
  <button onClick={exportToCSV} ...>Export CSV</button>  {/* NEW */}
  <button ...>Import</button>
  <button ...>Scan</button>
  <button ...>Add Device</button>
</div>
```

### Step 3: Handle Edge Cases

**Empty state:**
- Button disabled when `filteredDevices.length === 0`
- Tooltip explains why disabled

**Special characters in data:**
- CSV escaping handles commas, quotes, newlines in `sys_descr`
- Unicode characters preserved (UTF-8 BOM optional)

**Large exports:**
- Client-side handles up to 10,000 rows instantly
- For 50,000+ rows, consider streaming (not needed for this project)

---

## Advanced Features (Future Enhancement)

### Export All vs Export Filtered
Add dropdown button:
```typescript
<button>Export ▼</button>
<div className="dropdown">
  <button onClick={() => exportToCSV(false)}>Export filtered ({filteredDevices.length})</button>
  <button onClick={() => exportToCSV(true)}>Export all ({devices.length})</button>
</div>
```

### JSON Export
Add format selector:
```typescript
const [exportFormat, setExportFormat] = useState<'csv' | 'json'>('csv');
```

### Include Poll History
Add checkbox:
```typescript
<label>
  <input type="checkbox" checked={includeHistory} onChange={...} />
  Include poll history (last 24h)
</label>
```
This would require backend API call to fetch history per device.

### PDF Export
Use `jspdf` + `jspdf-autotable` for formatted PDF reports. More complex, lower priority.

---

## Database Changes

**No migration required.** Pure frontend feature.

---

## Testing

### Manual Testing
1. Navigate to `/devices` with 10+ devices
2. Click "Export CSV" → file downloads
3. Open CSV in Excel/Sheets → data formatted correctly
4. Apply filters → export only includes filtered devices
5. Export count shown in button: "Export CSV (12)"
6. Device with commas in `sys_descr` → properly escaped
7. Empty device list → button disabled

### Data Validation
- All 8 columns present in CSV
- Dates formatted as `YYYY-MM-DD HH:MM:SS`
- Network names resolved (not IDs)
- Empty fields exported as empty strings (not "null")

---

## Estimated Effort

| Task | Hours |
|------|-------|
| Implement `exportToCSV` function | 1h |
| Add export button to UI | 0.5h |
| CSV escaping edge cases | 0.5h |
| Disable state + tooltip | 0.5h |
| Manual testing | 0.5h |
| **Total** | **3h** |

---

## Notes

- **No backend changes** — pure frontend feature
- **CSV escaping** is critical — `sys_descr` often contains commas
- **Network name resolution** — export human-readable names, not UUIDs
- **Date formatting** — use ISO-like format for Excel compatibility
- **Future:** Add JSON export, PDF reports, scheduled exports
