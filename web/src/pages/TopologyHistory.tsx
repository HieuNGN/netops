import { useState } from 'react';
import { History, RefreshCw } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import { useTopologyHistory } from '../hooks/useTopologyHistory';

const EVENT_LABELS: Record<string, string> = {
  topology_change: 'Topology Change',
  node_added: 'Node Added',
  node_removed: 'Node Removed',
  link_added: 'Link Added',
  link_removed: 'Link Removed',
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
  const [limit, setLimit] = useState(100);
  const { events, isLoading } = useTopologyHistory(limit);
  const queryClient = useQueryClient();

  const handleRefresh = () => {
    queryClient.invalidateQueries({ queryKey: ['topologyHistory'] });
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-6 gap-4">
        <div>
          <h1 className="text-2xl font-bold text-[#161616] dark:text-white">Topology History</h1>
          <p className="text-[#525252] dark:text-[#a8a8a8] mt-1">
            Track network topology changes over time
          </p>
        </div>
        <div className="flex items-center space-x-2">
          <button
            onClick={handleRefresh}
            className="flex items-center space-x-2 px-4 py-2 bg-[#161616] text-white rounded-sm hover:bg-[#525252]"
          >
            <RefreshCw className="h-4 w-4" />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      <div className="bg-white dark:bg-[#262626] rounded-sm shadow-sm border border-[#e0e0e0] dark:border-[#393939] overflow-hidden">
        <div className="px-6 py-4 border-b border-[#e0e0e0] dark:border-[#393939] flex justify-between items-center">
          <h2 className="text-lg font-semibold text-[#161616] dark:text-white">Change Events</h2>
          <select
            value={limit}
            onChange={(e) => setLimit(parseInt(e.target.value))}
            className="px-2 py-1 border border-[#c6c6c6] dark:border-[#525252] bg-white dark:bg-[#262626] text-[#161616] dark:text-white rounded-sm text-sm"
          >
            <option value={50}>Last 50</option>
            <option value={100}>Last 100</option>
            <option value={250}>Last 250</option>
            <option value={500}>Last 500</option>
          </select>
        </div>

        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-[#e0e0e0] dark:divide-[#393939]">
            <thead className="bg-[#f4f4f4] dark:bg-[#161616]">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-[#525252] dark:text-[#a8a8a8] uppercase tracking-wider">
                  Time
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-[#525252] dark:text-[#a8a8a8] uppercase tracking-wider">
                  Event
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-[#525252] dark:text-[#a8a8a8] uppercase tracking-wider">
                  Description
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-[#525252] dark:text-[#a8a8a8] uppercase tracking-wider">
                  Status
                </th>
              </tr>
            </thead>
            <tbody className="bg-white dark:bg-[#262626] divide-y divide-[#e0e0e0] dark:divide-[#393939]">
              {isLoading ? (
                <tr>
                  <td colSpan={4} className="px-6 py-8 text-center text-[#525252] dark:text-[#a8a8a8]">
                    Loading history...
                  </td>
                </tr>
              ) : events.length === 0 ? (
                <tr>
                  <td colSpan={4} className="px-6 py-8 text-center text-[#525252] dark:text-[#a8a8a8]">
                    <div className="flex flex-col items-center justify-center">
                      <History className="h-8 w-8 mb-2 text-[#a8a8a8]" />
                      <p>No topology changes recorded yet.</p>
                      <p className="text-sm mt-1">
                        Changes will appear here when devices are added, removed, or links change.
                      </p>
                    </div>
                  </td>
                </tr>
              ) : (
                events.map((event) => (
                  <tr key={event.id} className="hover:bg-[#f4f4f4] dark:hover:bg-[#393939]">
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-[#525252] dark:text-[#a8a8a8] font-mono">
                      {formatDate(event.recorded_at)}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span className="inline-flex px-2 py-1 rounded-sm text-xs font-medium bg-[#e0e0e0] text-[#161616] dark:bg-[#262626] dark:text-[#f4f4f4]">
                        {EVENT_LABELS[event.event_type] || event.event_type}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-sm text-[#161616] dark:text-white">
                      {eventDescription(event)}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      {event.new_status ? (
                        <span
                          className={`inline-flex px-2 py-1 rounded-sm text-xs font-medium ${
                            event.new_status === 'online' || event.new_status === 'active'
                              ? 'bg-[#defbe6] text-[#24a148]'
                              : event.new_status === 'offline' || event.new_status === 'inactive'
                              ? 'bg-[#fff0f1] text-[#da1e28]'
                              : 'bg-[#e0e0e0] text-[#161616]'
                          }`}
                        >
                          {event.new_status}
                        </span>
                      ) : (
                        <span className="text-xs text-[#a8a8a8]">—</span>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

export default TopologyHistory;
