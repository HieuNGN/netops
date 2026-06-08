# Feature 2: Topology Filtering (Network/Status/Type)

## Problem Statement

The topology page renders all nodes and links with no way to filter. In networks with 30+ devices, the force-directed graph becomes an unreadable hairball. Every enterprise tool provides filtering — PRTG has map filters, SolarWinds has intelligent grouping, Datadog has tag-based filtering.

**Impact on presentation:** With simulated topology (8 devices) it looks fine. With real network (50+ devices) it's chaos. Professor asks "can you filter by network?" Answer: no. Looks incomplete.

---

## Current State

### Frontend
- `Topology.tsx` renders **all** nodes and links from `useTopology()` hook
- `useTopology()` fetches `GET /api/topology` → returns full topology
- No filter state, no filter UI
- Node data includes: `id`, `label`, `node_type`, `status`, `device_id`, `network_id` (via topology_nodes table)
- SSE stream pushes full topology updates → client replaces entire dataset

### Backend
- `GET /api/topology` returns `{ nodes: [...], links: [...] }`
- No query parameters for filtering
- Topology nodes have `network_id` column in DB
- Topology nodes have `status` and `node_type` columns

### Data Model
```
topology_nodes:
  - id, device_id, network_id, label, node_type, status
  
topology_links:
  - id, source_id, target_id, source_port, target_port, status
```

---

## Target State

### User Flow
1. User navigates to `/topology`
2. Filter bar appears below header with dropdowns:
   - **Network:** All / LAN / WAN / Wi-Fi / DMZ / ...
   - **Status:** All / Online / Offline / Unknown
   - **Node Type:** All / Router / Switch / Firewall / Device
3. Selecting a filter instantly hides non-matching nodes AND their orphaned links
4. Filter state persists in URL query params (shareable)
5. "Clear filters" button resets all
6. Filter count shown: "Showing 12 of 47 nodes"

### Filter Logic
- **Network filter:** Show nodes where `network_id` matches selected network
- **Status filter:** Show nodes where `status` matches (online/offline/unknown)
- **Type filter:** Show nodes where `node_type` matches (router/switch/firewall/device)
- **Combined:** AND logic — all active filters must match
- **Links:** Only show links where BOTH source and target nodes are visible

### Wireframe

```
┌─────────────────────────────────────────────────────────────────┐
│ Network Topology                          [Live] [Refresh]      │
│ 47 nodes • 62 links • Updated 12:34:56                         │
├─────────────────────────────────────────────────────────────────┤
│ [Network: LAN ▼] [Status: All ▼] [Type: All ▼]  clear · 12 shown │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│                    [Force Graph — filtered view]                │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Implementation Plan

### Approach: Client-Side Filtering Only

**Why not server-side?**
- Topology already streams via SSE — server-side filtering would break the stream contract
- Dataset is small (<500 nodes) — client-side is instant
- No backend changes needed — pure frontend feature
- Filters are visual-only — don't affect data collection

### Step 1: Add Filter State to Topology Page

**File:** `web/src/pages/Topology.tsx`

Add state:
```typescript
const [networkFilter, setNetworkFilter] = useState<string>('all');
const [statusFilter, setStatusFilter] = useState<string>('all');
const [typeFilter, setTypeFilter] = useState<string>('all');
```

### Step 2: Compute Filtered Graph Data

**File:** `web/src/pages/Topology.tsx`

Modify `graphData` useMemo:
```typescript
const graphData = useMemo(() => {
  // Filter nodes
  const filteredNodes = topology.nodes.filter((n) => {
    if (networkFilter !== 'all' && n.network_id !== networkFilter) return false;
    if (statusFilter !== 'all' && n.status !== statusFilter.toLowerCase()) return false;
    if (typeFilter !== 'all' && n.node_type !== typeFilter.toLowerCase()) return false;
    return true;
  });

  // Get set of visible node IDs
  const visibleNodeIds = new Set(filteredNodes.map((n) => n.id));

  // Filter links: only include if both source and target are visible
  const filteredLinks = topology.links.filter((l) => {
    const sourceId = typeof l.source_id === 'object' ? l.source_id.id : l.source_id;
    const targetId = typeof l.target_id === 'object' ? l.target_id.id : l.target_id;
    return visibleNodeIds.has(sourceId) && visibleNodeIds.has(targetId);
  });

  return {
    nodes: filteredNodes.map((n) => ({
      id: n.id,
      label: n.label || n.id,
      status: n.status,
      node_type: n.node_type,
      device_id: n.device_id,
      network_id: n.network_id,
      level: n.level ?? (n.node_type === 'firewall' ? 0 : n.node_type === 'router' ? 1 : n.node_type === 'switch' ? 3 : 2),
    })),
    links: filteredLinks.map((l) => ({
      source: l.source_id,
      target: l.target_id,
      source_port: l.source_port,
      target_port: l.target_port,
      status: l.status,
    })),
  };
}, [topology.nodes, topology.links, networkFilter, statusFilter, typeFilter]);
```

### Step 3: Add Filter UI

**File:** `web/src/pages/Topology.tsx`

Add filter bar below header (reuse `FilterSelect` pattern from Devices.tsx):

```typescript
// Extract unique networks and types for dropdown options
const networkOptions = useMemo(() => {
  const unique = Array.from(new Set(topology.nodes.map((n) => n.network_id).filter(Boolean)));
  return unique.map((id) => {
    const network = networks.find((n) => n.id === id);
    return { value: id, label: network?.name || id };
  });
}, [topology.nodes, networks]);

const typeOptions = [
  { value: 'router', label: 'Router' },
  { value: 'switch', label: 'Switch' },
  { value: 'firewall', label: 'Firewall' },
  { value: 'device', label: 'Device' },
];

const statusOptions = [
  { value: 'online', label: 'Online' },
  { value: 'offline', label: 'Offline' },
  { value: 'unknown', label: 'Unknown' },
];

const hasFilters = networkFilter !== 'all' || statusFilter !== 'all' || typeFilter !== 'all';
const clearFilters = () => {
  setNetworkFilter('all');
  setStatusFilter('all');
  setTypeFilter('all');
};
```

Render filter bar:
```typescript
<div className="border-b border-border px-6 py-3 bg-card">
  <div className="flex items-center gap-2 flex-wrap">
    <FilterSelect label="Network" value={networkFilter} onChange={setNetworkFilter} options={networkOptions} />
    <FilterSelect label="Status" value={statusFilter} onChange={setStatusFilter} options={statusOptions} />
    <FilterSelect label="Type" value={typeFilter} onChange={setTypeFilter} options={typeOptions} />
    {hasFilters && (
      <>
        <button onClick={clearFilters} className="text-xs px-2 py-1 text-muted-foreground hover:text-foreground">
          clear
        </button>
        <span className="text-xs text-muted-foreground ml-2">
          · <span className="text-foreground font-medium tabular-nums">{graphData.nodes.length}</span> of {topology.nodes.length} shown
        </span>
      </>
    )}
  </div>
</div>
```

### Step 4: Import Required Dependencies

**File:** `web/src/pages/Topology.tsx`

Add imports:
```typescript
import { useNetworks } from '../hooks';
```

Add hook call:
```typescript
const { networks } = useNetworks();
```

### Step 5: Extract FilterSelect Component

**File:** `web/src/components/ui/FilterSelect.tsx` (NEW)

Extract the `FilterSelect` component from `Devices.tsx` so it can be reused in Topology:

```typescript
export function FilterSelect({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
}) {
  const active = value !== 'all';
  return (
    <div
      className={`inline-flex items-center text-xs rounded-sm border overflow-hidden transition-colors ${
        active
          ? 'border-ibm-blue bg-ibm-blue/5 text-foreground'
          : 'border-input bg-card text-foreground'
      }`}
    >
      <span className={`px-2 py-1 font-medium ${active ? 'text-ibm-blue' : 'text-muted-foreground'}`}>
        {label}:
      </span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="bg-transparent px-1.5 py-1 text-xs text-foreground focus:outline-none cursor-pointer"
      >
        <option value="all">all</option>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </div>
  );
}
```

Update `Devices.tsx` to import from `../components/ui/FilterSelect`.

---

## Database Changes

**No migration required.** Uses existing `network_id`, `status`, `node_type` columns on `topology_nodes`.

---

## Edge Cases

1. **No nodes match filters** → Show "No nodes match the current filters" message with clear button
2. **All nodes filtered out** → Links automatically hidden (both endpoints must be visible)
3. **Network filter with no network_id** → Nodes without network_id only show when filter is "all"
4. **SSE update while filtered** → Filter re-applies automatically (useMemo dependency)
5. **Empty topology** → Filter bar hidden when `topology.nodes.length === 0`

---

## Testing

### Manual Testing
1. Navigate to `/topology` with 10+ nodes
2. Select "Network: LAN" → only LAN nodes visible
3. Select "Status: Offline" → only offline nodes visible
4. Combine filters → AND logic works
5. Click "clear" → all nodes reappear
6. Filter count updates correctly
7. Links disappear when one endpoint is filtered out
8. SSE stream continues working while filters active

### Visual Testing
- Filter bar doesn't break on mobile (flex-wrap)
- Dark mode colors correct
- Filter dropdowns accessible (keyboard navigation)

---

## Estimated Effort

| Task | Hours |
|------|-------|
| Extract `FilterSelect` component | 0.5h |
| Update `Devices.tsx` to use shared component | 0.5h |
| Add filter state to `Topology.tsx` | 1h |
| Implement filtering logic in `useMemo` | 1.5h |
| Add filter bar UI | 1.5h |
| Edge case handling (no matches, empty state) | 1h |
| **Total** | **6h** |

---

## Notes

- **No backend changes** — pure frontend feature
- **Performance:** Client-side filtering is instant for <500 nodes
- **SSE compatibility:** Filters re-apply automatically on data update
- **Reusable component:** `FilterSelect` can be used in other pages (Checks, Alerts)
