import { Activity, Server, Network, CheckCircle, AlertCircle, ArrowUpCircle, ArrowDownCircle, Bell, Check, X, History } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useTopology } from '../hooks/useTopology';
import { useDevices } from '../hooks/useDevices';
import { useChecks } from '../hooks/useChecks';
import { useActiveAlerts } from '../hooks/useActiveAlerts';
import { usePollHistory } from '../hooks/usePollHistory';
import { useTopologyHistory } from '../hooks/useTopologyHistory';
import { LineChart, Line, PieChart, Pie, Cell, ResponsiveContainer, XAxis, YAxis, Tooltip, Legend, BarChart, Bar } from 'recharts';

function StatCard({ title, value, subtext, icon: Icon, color, trend }: any) {
  return (
    <div className="bg-white dark:bg-[#262626] rounded-sm shadow-sm border border-[#e0e0e0] dark:border-[#393939] p-6">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium text-[#525252] dark:text-[#a8a8a8]">{title}</p>
          <p className="text-3xl font-bold text-[#161616] dark:text-white mt-2">{value}</p>
          {subtext && <p className="text-sm text-[#525252] dark:text-[#a8a8a8] mt-1">{subtext}</p>}
          {trend && (
            <div className={`flex items-center mt-2 text-sm ${trend > 0 ? 'text-[#24a148]' : 'text-[#da1e28]'}`}>
              {trend > 0 ? <ArrowUpCircle className="h-4 w-4 mr-1" /> : <ArrowDownCircle className="h-4 w-4 mr-1" />}
              <span>{Math.abs(trend)}% from last hour</span>
            </div>
          )}
        </div>
        <div className={`p-3 rounded-sm ${color}`}>
          <Icon className="h-6 w-6 text-white" />
        </div>
      </div>
    </div>
  );
}

// Mock data for charts (will be replaced with real API data in production)
const generatePollData = () => {
  const now = Date.now();
  return Array.from({ length: 12 }, (_, i) => ({
    time: new Date(now - (11 - i) * 5 * 60000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    success: Math.floor(Math.random() * 80) + 20,
    failed: Math.floor(Math.random() * 20),
  }));
};

export function Dashboard() {
  const { topology } = useTopology();
  const { devices } = useDevices();
  const { checks } = useChecks();
  const { alerts: activeAlerts, acknowledge, resolve } = useActiveAlerts();
  const { history: pollHistory, isLoading: pollHistoryLoading } = usePollHistory(250);
  const { events: topologyEvents, isLoading: topologyEventsLoading } = useTopologyHistory(20);

  const deviceStats = {
    online: devices.filter((d) => d.status === 'online').length,
    offline: devices.filter((d) => d.status === 'offline').length,
    unknown: devices.filter((d) => d.status === 'unknown').length,
  };

  const deviceStatusData = [
    { name: 'Online', value: deviceStats.online, status: 'online' },
    { name: 'Offline', value: deviceStats.offline, status: 'offline' },
    { name: 'Unknown', value: deviceStats.unknown, status: 'unknown' },
  ].filter(d => d.value > 0);

  const pollData = generatePollData();

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-[#161616] dark:text-white">Dashboard</h1>
        <p className="text-[#525252] dark:text-[#a8a8a8] mt-1">Network overview and health status</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        <StatCard
          title="Total Devices"
          value={devices.length}
          subtext={`${deviceStats.online} online, ${deviceStats.offline} offline`}
          icon={Server}
          color="bg-[#0f62fe]"
        />
        <StatCard
          title="Network Nodes"
          value={topology.nodes.length}
          subtext={`${topology.links.length} active links`}
          icon={Network}
          color="bg-[#161616]"
        />
        <StatCard
          title="Service Checks"
          value={checks.length}
          subtext="Active monitoring"
          icon={Activity}
          color="bg-[#24a148]"
        />
        <StatCard
          title="System Status"
          value={deviceStats.offline > 0 ? 'Issues' : 'Healthy'}
          subtext={deviceStats.offline > 0 ? `${deviceStats.offline} devices offline` : 'All systems operational'}
          icon={deviceStats.offline > 0 ? AlertCircle : CheckCircle}
          color={deviceStats.offline > 0 ? 'bg-[#da1e28]' : 'bg-[#24a148]'}
        />
      </div>

      {/* Active Alerts Banner */}
      {activeAlerts.length > 0 && (
        <div className="mb-6 bg-white dark:bg-[#262626] rounded-sm shadow-sm border border-[#e0e0e0] dark:border-[#393939] p-6">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-lg font-semibold text-[#161616] dark:text-white flex items-center space-x-2">
              <Bell className="h-5 w-5 text-[#da1e28]" />
              <span>Active Alerts</span>
              <span className="px-2 py-0.5 bg-[#da1e28] text-white text-xs rounded-sm font-medium">
                {activeAlerts.length}
              </span>
            </h2>
            <Link
              to="/alerts"
              className="text-sm text-[#161616] dark:text-[#a8a8a8] hover:text-[#161616] dark:hover:text-[#f4f4f4]"
            >
              View all →
            </Link>
          </div>
          <div className="space-y-2">
            {activeAlerts.map((alert) => (
              <div
                key={alert.key}
                className={`flex items-center justify-between p-3 rounded-sm border ${
                  alert.status === 'firing'
                    ? 'bg-[#fff0f1] dark:bg-[#520408] border-[#da1e28] dark:border-[#ff8389]'
                    : 'bg-[#fcf4d6] dark:bg-[#483501] border-[#b28600]'
                }`}
              >
                <div className="flex items-start space-x-3">
                  <div className="mt-0.5">
                    <span
                      className={`inline-flex px-2 py-0.5 text-xs rounded-sm font-medium ${
                        alert.severity === 'critical'
                          ? 'bg-[#da1e28] text-white'
                          : alert.severity === 'warning'
                          ? 'bg-[#f1c21b] text-[#161616]'
                          : 'bg-[#e0e0e0] text-[#161616]'
                      }`}
                    >
                      {alert.severity}
                    </span>
                  </div>
                  <div>
                    <p className="text-sm font-medium text-[#161616] dark:text-white">{alert.title}</p>
                    <p className="text-xs text-[#525252] dark:text-[#a8a8a8]">{alert.message}</p>
                    <p className="text-xs text-[#a8a8a8] dark:text-[#525252] mt-0.5">
                      {alert.status === 'acknowledged' && (
                        <span className="text-[#b28600] font-medium">Acknowledged · </span>
                      )}
                      Fired {new Date(alert.fired_at * 1000).toLocaleTimeString()}
                    </p>
                  </div>
                </div>
                <div className="flex items-center space-x-1">
                  {alert.status === 'firing' && (
                    <button
                      onClick={() => acknowledge(alert.key)}
                      className="p-1.5 text-[#525252] dark:text-[#a8a8a8] hover:bg-[#e0e0e0] dark:hover:bg-[#393939] rounded-sm"
                      title="Acknowledge"
                    >
                      <Check className="h-4 w-4" />
                    </button>
                  )}
                  <button
                    onClick={() => resolve(alert.key)}
                    className="p-1.5 text-[#da1e28] dark:text-[#ff8389] hover:bg-[#fff0f1] dark:hover:bg-[#520408] rounded-sm"
                    title="Resolve"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Recent Devices */}
        <div className="bg-white dark:bg-[#262626] rounded-sm shadow-sm border border-[#e0e0e0] dark:border-[#393939] p-6">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-lg font-semibold text-[#161616] dark:text-white">Devices</h2>
            <Link to="/devices" className="text-sm text-[#161616] dark:text-[#a8a8a8] hover:text-[#161616] dark:hover:text-[#f4f4f4]">
              View all →
            </Link>
          </div>
          {devices.length === 0 ? (
            <p className="text-[#525252] dark:text-[#a8a8a8] text-sm">No devices configured</p>
          ) : (
            <div className="space-y-3">
              {devices.slice(0, 5).map((device) => (
                <div
                  key={device.id}
                  className="flex items-center justify-between py-2 border-b border-[#f4f4f4] dark:border-[#393939] last:border-0"
                >
                  <div>
                    <p className="font-medium text-[#161616] dark:text-white">{device.name || device.ip_address}</p>
                    <p className="text-sm text-[#525252] dark:text-[#a8a8a8]">{device.ip_address}</p>
                  </div>
                  <span
                    className={`px-2 py-1 rounded-sm text-xs font-medium ${
                      device.status === 'online'
                        ? 'bg-[#defbe6] text-[#24a148]'
                        : device.status === 'offline'
                        ? 'bg-[#fff0f1] text-[#da1e28]'
                        : 'bg-[#e0e0e0] text-[#161616]'
                    }`}
                  >
                    {device.status}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Service Checks Summary */}
        <div className="bg-white dark:bg-[#262626] rounded-sm shadow-sm border border-[#e0e0e0] dark:border-[#393939] p-6">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-lg font-semibold text-[#161616] dark:text-white">Service Checks</h2>
            <Link to="/checks" className="text-sm text-[#161616] dark:text-[#a8a8a8] hover:text-[#161616] dark:hover:text-[#f4f4f4]">
              View all →
            </Link>
          </div>
          {checks.length === 0 ? (
            <p className="text-[#525252] dark:text-[#a8a8a8] text-sm">No service checks configured</p>
          ) : (
            <div className="space-y-3">
              {checks.slice(0, 5).map((check) => (
                <div
                  key={check.id}
                  className="flex items-center justify-between py-2 border-b border-[#f4f4f4] dark:border-[#393939] last:border-0"
                >
                  <div>
                    <p className="font-medium text-[#161616] dark:text-white">{check.name}</p>
                    <p className="text-sm text-[#525252] dark:text-[#a8a8a8]">
                      {check.check_type} • {check.target}
                    </p>
                  </div>
                  <span
                    className={`px-2 py-1 rounded-sm text-xs font-medium ${
                      check.enabled
                        ? 'bg-[#defbe6] text-[#24a148]'
                        : 'bg-[#e0e0e0] text-[#161616]'
                    }`}
                  >
                    {check.enabled ? 'Active' : 'Disabled'}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-6">
        {/* Device Status Distribution */}
        <div className="bg-white dark:bg-[#262626] rounded-sm shadow-sm border border-[#e0e0e0] dark:border-[#393939] p-6">
          <h2 className="text-lg font-semibold text-[#161616] dark:text-white mb-4">Device Status Distribution</h2>
          {deviceStatusData.length === 0 ? (
            <p className="text-[#525252] dark:text-[#a8a8a8] text-sm text-center py-8">No devices to display</p>
          ) : (
            <ResponsiveContainer width="100%" height={250}>
              <PieChart>
                <Pie
                  data={deviceStatusData}
                  cx="50%"
                  cy="50%"
                  labelLine={false}
                  label={({ name, value }) => `${name}: ${value}`}
                  outerRadius={80}
                  fill="#8884d8"
                  dataKey="value"
                >
                  {deviceStatusData.map((entry, index) => (
                    <Cell
                      key={`cell-${index}`}
                      fill={entry.status === 'online' ? '#22c55e' : entry.status === 'offline' ? '#ef4444' : '#6b7280'}
                    />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{
                    backgroundColor: 'rgb(31, 41, 55)',
                    border: 'none',
                    borderRadius: '8px',
                    color: '#fff',
                  }}
                />
              </PieChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Poll Success Rate */}
        <div className="bg-white dark:bg-[#262626] rounded-sm shadow-sm border border-[#e0e0e0] dark:border-[#393939] p-6">
          <h2 className="text-lg font-semibold text-[#161616] dark:text-white mb-4">Poll Success Rate (Last Hour)</h2>
          <ResponsiveContainer width="100%" height={250}>
            <LineChart data={pollData}>
              <XAxis dataKey="time" stroke="#6b7280" fontSize={12} />
              <YAxis stroke="#6b7280" fontSize={12} />
              <Tooltip
                contentStyle={{
                  backgroundColor: 'rgb(31, 41, 55)',
                  border: 'none',
                  borderRadius: '8px',
                  color: '#fff',
                }}
              />
              <Legend />
              <Line type="monotone" dataKey="success" stroke="#22c55e" strokeWidth={2} name="Success" />
              <Line type="monotone" dataKey="failed" stroke="#ef4444" strokeWidth={2} name="Failed" />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Device Uptime Chart */}
      <div className="bg-white dark:bg-[#262626] rounded-sm shadow-sm border border-[#e0e0e0] dark:border-[#393939] p-6 mt-6">
        <h2 className="text-lg font-semibold text-[#161616] dark:text-white mb-4">Device Uptime (Last 250 Polls)</h2>
        {pollHistoryLoading || pollHistory.length === 0 ? (
          <p className="text-[#525252] dark:text-[#a8a8a8] text-sm text-center py-8">No poll history available</p>
        ) : (
          (() => {
            // Aggregate uptime % per device
            const deviceStats: Record<string, { name: string; total: number; online: number }> = {};
            for (const entry of pollHistory) {
              const id = entry.device_id;
              if (!deviceStats[id]) {
                deviceStats[id] = { name: entry.name || entry.ip_address || id, total: 0, online: 0 };
              }
              deviceStats[id].total += 1;
              if (entry.status === 'online') {
                deviceStats[id].online += 1;
              }
            }
            const uptimeData = Object.values(deviceStats)
              .map((d) => ({
                name: d.name,
                uptime: Math.round((d.online / d.total) * 100),
              }))
              .sort((a, b) => a.name.localeCompare(b.name));
            return (
              <ResponsiveContainer width="100%" height={250}>
                <BarChart data={uptimeData}>
                  <XAxis dataKey="name" stroke="#6b7280" fontSize={12} angle={-30} textAnchor="end" height={60} />
                  <YAxis stroke="#6b7280" fontSize={12} domain={[0, 100]} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: 'rgb(31, 41, 55)',
                      border: 'none',
                      borderRadius: '8px',
                      color: '#fff',
                    }}
                  />
                  <Bar dataKey="uptime" fill="#24a148" name="Uptime %" />
                </BarChart>
              </ResponsiveContainer>
            );
          })()
        )}
      </div>

      {/* Recent Topology Changes */}
      <div className="bg-white dark:bg-[#262626] rounded-sm shadow-sm border border-[#e0e0e0] dark:border-[#393939] p-6 mt-6">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-lg font-semibold text-[#161616] dark:text-white flex items-center space-x-2">
            <History className="h-5 w-5 text-[#0f62fe] dark:text-[#78a9ff]" />
            <span>Recent Topology Changes</span>
          </h2>
          <Link
            to="/topology/history"
            className="text-sm text-[#161616] dark:text-[#a8a8a8] hover:text-[#161616] dark:hover:text-[#f4f4f4]"
          >
            View all →
          </Link>
        </div>
        {topologyEventsLoading || topologyEvents.length === 0 ? (
          <p className="text-[#525252] dark:text-[#a8a8a8] text-sm text-center py-8">No topology changes recorded</p>
        ) : (
          <div className="space-y-2">
            {topologyEvents.slice(0, 10).map((event) => (
              <div
                key={event.id}
                className="flex items-center justify-between py-2 border-b border-[#f4f4f4] dark:border-[#393939] last:border-0"
              >
                <div className="flex items-center space-x-3">
                  <span
                    className={`inline-flex px-2 py-0.5 text-xs rounded-sm font-medium ${
                      event.event_type === 'node_added'
                        ? 'bg-[#defbe6] text-[#24a148]'
                        : event.event_type === 'node_removed'
                        ? 'bg-[#fff0f1] text-[#da1e28]'
                        : event.event_type === 'link_added'
                        ? 'bg-[#e8f0fe] text-[#0f62fe]'
                        : event.event_type === 'link_removed'
                        ? 'bg-[#fff0f1] text-[#da1e28]'
                        : 'bg-[#e0e0e0] text-[#161616]'
                    }`}
                  >
                    {event.event_type}
                  </span>
                  <span className="text-sm text-[#161616] dark:text-white">
                    {event.node_id || event.link_id || 'Topology'}
                  </span>
                </div>
                <span className="text-xs text-[#a8a8a8] dark:text-[#525252]">
                  {new Date(event.recorded_at).toLocaleString()}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Topology Stats */}
      <div className="bg-white dark:bg-[#262626] rounded-sm shadow-sm border border-[#e0e0e0] dark:border-[#393939] p-6 mt-6">
        <h2 className="text-lg font-semibold text-[#161616] dark:text-white mb-4">Topology Overview</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="text-center p-4 bg-[#f4f4f4] dark:bg-[#262626] rounded-sm">
            <p className="text-2xl font-bold text-[#161616] dark:text-[#a8a8a8]">{topology.nodes.length}</p>
            <p className="text-sm text-[#525252] dark:text-[#a8a8a8] mt-1">Total Nodes</p>
          </div>
          <div className="text-center p-4 bg-[#f4f4f4] dark:bg-[#262626] rounded-sm">
            <p className="text-2xl font-bold text-cyan-600 dark:text-cyan-400">{topology.links.length}</p>
            <p className="text-sm text-[#525252] dark:text-[#a8a8a8] mt-1">Active Links</p>
          </div>
          <div className="text-center p-4 bg-[#f4f4f4] dark:bg-[#262626] rounded-sm">
            <p className="text-2xl font-bold text-[#24a148] dark:text-[#42be65]">
              {topology.nodes.filter((n) => n.status === 'online').length}
            </p>
            <p className="text-sm text-[#525252] dark:text-[#a8a8a8] mt-1">Online Nodes</p>
          </div>
          <div className="text-center p-4 bg-[#f4f4f4] dark:bg-[#262626] rounded-sm">
            <p className="text-2xl font-bold text-[#0f62fe] dark:text-[#78a9ff]">
              {topology.links.filter((l) => l.status === 'active').length}
            </p>
            <p className="text-sm text-[#525252] dark:text-[#a8a8a8] mt-1">Active Connections</p>
          </div>
        </div>
      </div>
    </div>
  );
}

export default Dashboard;
