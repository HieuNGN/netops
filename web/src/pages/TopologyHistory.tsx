import { useState, lazy, Suspense } from 'react';
import { History, RefreshCw, GitCompare } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import { useTopologyHistory } from '../hooks/useTopologyHistory';
import { topologyApi } from '../api';

const TopologyDiff = lazy(() => import('../components/TopologyDiff'));

const EVENT_LABELS: Record<string, string> = {
  topology_change: 'Topology Change',
  node_added: 'Node Added',
  node_removed: 'Node Removed',
  link_added: 'Link Added',
  link_removed: 'Link Removed',
  status_change: 'Status Change',
};

function formatDate(iso: string) {
  const d = new Date(iso);
  return d.toLocaleString();
}

function eventDescription(event: {
  event_type: string;
  node_id: string | null;
  link_id: string | null;
  old_status: string | null;
  new_status: string | null;
  details: Record<string, any>;
}): string {
  const details = event.details || {};
  if (details.type === 'node' && details.action === 'added') {
    return `Node ${event.node_id || 'unknown'} added`;
  }
  if (details.type === 'link' && details.action === 'added') {
    return `Link ${event.link_id || 'unknown'} added`;
  }
  if (details.type === 'nodes' && details.action === 'removed') {
    return `${details.count || 0} node(s) removed`;
  }
  if (details.type === 'links' && details.action === 'removed') {
    return `${details.count || 0} link(s) removed`;
  }
  if (event.old_status && event.new_status) {
    return `Status changed from ${event.old_status} to ${event.new_status}`;
  }
  return EVENT_LABELS[event.event_type] || event.event_type;
}

export function TopologyHistory() {
  const [filters, setFilters] = useState({
    limit: 100,
    event_type: '',
    from_time: '',
    to_time: '',
    offset: 0,
  });
  const [diffEvent, setDiffEvent] = useState<{ before: any; after: any; event: any } | null>(null);
  const { events, total, isLoading } = useTopologyHistory(filters);
  const queryClient = useQueryClient();

  const handleRefresh = () => {
    queryClient.invalidateQueries({ queryKey: ['topologyHistory'] });
  };

  const handleViewDiff = async (event: any) => {
    const { data } = await topologyApi.snapshot(event.id);
    setDiffEvent({ before: data.topology, after: data.current || data.topology, event });
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-6 gap-4">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Topology History</h1>
          <p className="text-muted-foreground mt-1">Track network topology changes over time</p>
        </div>
        <div className="flex items-center space-x-2">
          <button
            onClick={handleRefresh}
            className="flex items-center space-x-2 px-4 py-2 bg-cisco-teal text-white rounded-sm hover:bg-cisco-teal/70"
          >
            <RefreshCw className="h-4 w-4" />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="bg-card rounded-sm border border-border p-4 mb-6 flex flex-wrap gap-3 items-end">
        <div>
          <label className="block text-xs font-medium text-muted-foreground mb-1">Event Type</label>
          <select
            value={filters.event_type}
            onChange={(e) => setFilters(f => ({ ...f, event_type: e.target.value, offset: 0 }))}
            className="px-2 py-1 border border-input bg-card text-foreground rounded-sm text-sm"
          >
            <option value="">All</option>
            <option value="topology_change">Topology Change</option>
            <option value="node_added">Node Added</option>
            <option value="node_removed">Node Removed</option>
            <option value="link_added">Link Added</option>
            <option value="link_removed">Link Removed</option>
          </select>
        </div>
        <div>
          <label className="block text-xs font-medium text-muted-foreground mb-1">From</label>
          <input
            type="datetime-local"
            value={filters.from_time}
            onChange={(e) => setFilters(f => ({ ...f, from_time: e.target.value, offset: 0 }))}
            className="px-2 py-1 border border-input bg-card text-foreground rounded-sm text-sm"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-muted-foreground mb-1">To</label>
          <input
            type="datetime-local"
            value={filters.to_time}
            onChange={(e) => setFilters(f => ({ ...f, to_time: e.target.value, offset: 0 }))}
            className="px-2 py-1 border border-input bg-card text-foreground rounded-sm text-sm"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-muted-foreground mb-1">Limit</label>
          <select
            value={filters.limit}
            onChange={(e) => setFilters(f => ({ ...f, limit: parseInt(e.target.value), offset: 0 }))}
            className="px-2 py-1 border border-input bg-card text-foreground rounded-sm text-sm"
          >
            <option value={50}>50</option>
            <option value={100}>100</option>
            <option value={250}>250</option>
            <option value={500}>500</option>
          </select>
        </div>
        <button
          onClick={() => setFilters({ limit: 100, event_type: '', from_time: '', to_time: '', offset: 0 })}
          className="px-3 py-1 text-sm text-muted-foreground hover:text-foreground border border-input rounded-sm"
        >
          Reset
        </button>
      </div>

      {/* Diff Modal */}
      {diffEvent && (
        <div className="fixed inset-0 z-50 bg-foreground/20 flex items-center justify-center p-4">
          <div className="bg-card rounded-sm shadow-lg border border-border w-full max-w-5xl h-[80vh] flex flex-col">
            <div className="px-4 py-3 border-b border-border flex justify-between items-center">
              <h3 className="font-semibold text-foreground">Topology Diff — {formatDate(diffEvent.event.recorded_at)}</h3>
              <button onClick={() => setDiffEvent(null)} className="text-muted-foreground hover:text-foreground">×</button>
            </div>
            <div className="flex-1 overflow-hidden">
              <Suspense fallback={<div className="p-4 text-muted-foreground">Loading diff…</div>}>
                <TopologyDiff before={diffEvent.before} after={diffEvent.after} event={diffEvent.event} />
              </Suspense>
            </div>
          </div>
        </div>
      )}

      <div className="bg-card rounded-sm shadow-sm border border-border overflow-hidden">
        <div className="px-6 py-4 border-b border-border flex justify-between items-center">
          <h2 className="text-lg font-semibold text-foreground">Change Events ({total})</h2>
        </div>

        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-border">
            <thead className="bg-background">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">Time</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">Event</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">Description</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">Status</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody className="bg-card divide-y divide-border">
              {isLoading ? (
                <tr><td colSpan={5} className="px-6 py-8 text-center text-muted-foreground">Loading history…</td></tr>
              ) : events.length === 0 ? (
                <tr><td colSpan={5} className="px-6 py-8 text-center text-muted-foreground">
                  <div className="flex flex-col items-center justify-center">
                    <History className="h-8 w-8 mb-2 text-muted-foreground" />
                    <p>No topology changes recorded yet.</p>
                  </div>
                </td></tr>
              ) : (
                events.map((event) => (
                  <tr key={event.id} className="hover:bg-muted">
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-muted-foreground font-mono">{formatDate(event.recorded_at)}</td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span className="inline-flex px-2 py-1 rounded-sm text-xs font-medium bg-muted text-foreground">
                        {EVENT_LABELS[event.event_type] || event.event_type}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-sm text-foreground">{eventDescription(event)}</td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      {event.new_status ? (
                        <span className={`inline-flex px-2 py-1 rounded-sm text-xs font-medium ${
                          event.new_status === 'online' || event.new_status === 'active'
                            ? 'bg-success/10 text-success'
                            : event.new_status === 'offline' || event.new_status === 'inactive'
                            ? 'bg-destructive/10 text-destructive'
                            : 'bg-muted text-foreground'
                        }`}>
                          {event.new_status}
                        </span>
                      ) : (
                        <span className="text-xs text-muted-foreground">—</span>
                      )}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <button
                        onClick={() => handleViewDiff(event)}
                        className="flex items-center space-x-1 text-xs text-info hover:text-info/80"
                      >
                        <GitCompare className="h-3 w-3" />
                        <span>Diff</span>
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {total > filters.limit && (
          <div className="px-6 py-3 border-t border-border flex justify-between items-center">
            <button
              disabled={filters.offset === 0}
              onClick={() => setFilters(f => ({ ...f, offset: Math.max(0, f.offset - f.limit) }))}
              className="px-3 py-1 text-sm text-foreground border border-input rounded-sm disabled:opacity-50"
            >
              Previous
            </button>
            <span className="text-sm text-muted-foreground">
              {filters.offset + 1}–{Math.min(filters.offset + filters.limit, total)} of {total}
            </span>
            <button
              disabled={filters.offset + filters.limit >= total}
              onClick={() => setFilters(f => ({ ...f, offset: f.offset + f.limit }))}
              className="px-3 py-1 text-sm text-foreground border border-input rounded-sm disabled:opacity-50"
            >
              Next
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

export default TopologyHistory;
