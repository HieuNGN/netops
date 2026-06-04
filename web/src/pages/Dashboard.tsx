import { useState } from 'react';
import { Activity, Server, Network, CheckCircle, AlertCircle, ArrowUpCircle, ArrowDownCircle, Bell, Check, X, History, Settings } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useTopology } from '../hooks/useTopology';
import { useDevices } from '../hooks/useDevices';
import { useChecks } from '../hooks/useChecks';
import { useActiveAlerts } from '../hooks/useActiveAlerts';
import { usePollHistory } from '../hooks/usePollHistory';
import { useTopologyHistory } from '../hooks/useTopologyHistory';
import { NetworkPicker } from '../components/NetworkPicker';
import { NetworksConsole } from '../components/NetworksConsole';
import { LineChart, Line, PieChart, Pie, Cell, ResponsiveContainer, XAxis, YAxis, Tooltip, Legend, BarChart, Bar } from 'recharts';

function StatCard({ title, value, subtext, icon: Icon, colorClass, trend }: any) {
  return (
    <div className="bg-card rounded-sm shadow-sm border border-border p-6">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium text-muted-foreground">{title}</p>
          <p className="text-3xl font-bold text-foreground mt-2">{value}</p>
          {subtext && <p className="text-sm text-muted-foreground mt-1">{subtext}</p>}
          {trend && (
            <div className={`flex items-center mt-2 text-sm ${trend > 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-destructive'}`}>
              {trend > 0 ? <ArrowUpCircle className="h-4 w-4 mr-1" /> : <ArrowDownCircle className="h-4 w-4 mr-1" />}
              <span>{Math.abs(trend)}% from last hour</span>
            </div>
          )}
        </div>
        <div className={`p-3 rounded-sm ${colorClass}`}>
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
  const [drawerOpen, setDrawerOpen] = useState(false);
  const { topology } = useTopology();
  const { devices } = useDevices();
  const { checks } = useChecks();
  const { alerts: activeAlerts, acknowledge, resolve } = useActiveAlerts();
  const { history: pollHistory, isLoading: pollHistoryLoading } = usePollHistory(250);
  const { events: topologyEvents, isLoading: topologyEventsLoading } = useTopologyHistory({ limit: 20 });

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
        <h1 className="text-2xl font-bold text-foreground">Dashboard</h1>
        <p className="text-muted-foreground mt-1">Network overview and health status</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        <StatCard
          title="Total Devices"
          value={devices.length}
          subtext={`${deviceStats.online} online, ${deviceStats.offline} offline`}
          icon={Server}
          colorClass="bg-btn-accent text-btn-accent-foreground"
        />
        <StatCard
          title="Network Nodes"
          value={topology.nodes.length}
          subtext={`${topology.links.length} active links`}
          icon={Network}
          colorClass="bg-btn-primary text-btn-primary-foreground"
        />
        <StatCard
          title="Service Checks"
          value={checks.length}
          subtext="Active monitoring"
          icon={Activity}
          colorClass="bg-btn-success text-btn-success-foreground"
        />
        <StatCard
          title="System Status"
          value={deviceStats.offline > 0 ? 'Issues' : 'Healthy'}
          subtext={deviceStats.offline > 0 ? `${deviceStats.offline} devices offline` : 'All systems operational'}
          icon={deviceStats.offline > 0 ? AlertCircle : CheckCircle}
          colorClass={deviceStats.offline > 0 ? 'bg-btn-destructive text-btn-destructive-foreground' : 'bg-btn-success text-btn-success-foreground'}
        />
      </div>

      {/* Active Alerts Banner */}
      {activeAlerts.length > 0 && (
        <div className="mb-6 bg-card rounded-sm shadow-sm border border-border p-6">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-lg font-semibold text-foreground flex items-center space-x-2">
              <Bell className="h-5 w-5 text-destructive" />
              <span>Active Alerts</span>
              <span className="px-2 py-0.5 bg-btn-destructive text-btn-destructive-foreground text-xs rounded-sm font-medium">
                {activeAlerts.length}
              </span>
            </h2>
            <Link to="/alerts" className="text-sm text-info hover:underline">View all &rarr;</Link>
          </div>
          <div className="space-y-2">
            {activeAlerts.map((alert) => (
              <div key={alert.key} className={`flex items-center justify-between p-3 rounded-sm border ${alert.status === 'firing' ? 'bg-red-50 dark:bg-destructive/20 border-red-500 dark:border-destructive' : 'bg-yellow-100 dark:bg-warning/20 border-yellow-500 dark:border-warning'}`}>
                <div className="flex items-start space-x-3">
                  <div className="mt-0.5">
                    <span className={`inline-flex px-2 py-0.5 text-xs rounded-sm font-medium ${
                    alert.severity === 'critical'
                      ? 'bg-btn-destructive text-btn-destructive-foreground dark:bg-red-600'
                      : alert.severity === 'warning'
                      ? 'bg-warning text-foreground dark:bg-yellow-500'
                      : 'bg-secondary text-foreground dark:bg-muted dark:text-muted-foreground'
                  }`}>{alert.severity}</span>
                  </div>
                  <div>
                    <p className="text-sm font-medium text-foreground">{alert.title}</p>
                    <p className="text-xs text-muted-foreground">{alert.message}</p>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      {alert.status === 'acknowledged' && <span className="text-warning-foreground font-medium">Acknowledged &middot; </span>}
                      Fired {new Date(alert.fired_at * 1000).toLocaleTimeString()}
                    </p>
                  </div>
                </div>
                <div className="flex items-center space-x-1">
                  {alert.status === 'firing' && (
                    <button onClick={() => acknowledge(alert.key)} className="p-1.5 text-muted-foreground hover:bg-surface-hover rounded-sm" title="Acknowledge"><Check className="h-4 w-4" /></button>
                  )}
                  <button onClick={() => resolve(alert.key)} className="p-1.5 text-destructive hover:bg-badge-destructive-bg rounded-sm" title="Resolve"><X className="h-4 w-4" /></button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Network Management */}
      <div className="mb-8 bg-card rounded-sm shadow-sm border border-border p-6 max-w-md">
        <NetworkPicker />
        <div className="mt-3 pt-3 border-t border-border">
          <button
            onClick={() => setDrawerOpen(true)}
            className="flex items-center gap-1.5 text-sm px-3 py-1.5 bg-btn-accent text-btn-accent-foreground rounded-sm hover:bg-btn-accent-hover"
          >
            <Settings className="h-3.5 w-3.5" />
            Manage Networks
          </button>
        </div>
      </div>

      <NetworksConsole open={drawerOpen} onClose={() => setDrawerOpen(false)} />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Recent Devices */}
        <div className="bg-card rounded-sm shadow-sm border border-border p-6">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-lg font-semibold text-foreground">Devices</h2>
            <Link to="/devices" className="text-sm text-foreground hover:text-foreground dark:hover:text-foreground">
              View all →
            </Link>
          </div>
          {devices.length === 0 ? (
            <p className="text-muted-foreground text-sm">No devices configured</p>
          ) : (
            <div className="space-y-3">
              {devices.slice(0, 5).map((device) => (
                <div
                  key={device.id}
                  className="flex items-center justify-between py-2 border-b border-border last:border-0"
                >
                  <div>
                    <p className="font-medium text-foreground">{device.name || device.ip_address}</p>
                    <p className="text-sm text-muted-foreground">{device.ip_address}</p>
                  </div>
                  <span
                    className={`px-2 py-1 rounded-sm text-xs font-medium ${
                      device.status === 'online'
                        ? 'bg-badge-success-bg text-badge-success-fg'
                        : device.status === 'offline'
                        ? 'bg-badge-destructive-bg text-badge-destructive-fg'
                        : 'bg-badge-neutral-bg text-badge-neutral-fg'
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
        <div className="bg-card rounded-sm shadow-sm border border-border p-6">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-lg font-semibold text-foreground">Service Checks</h2>
            <Link to="/checks" className="text-sm text-foreground hover:text-foreground dark:hover:text-foreground">
              View all →
            </Link>
          </div>
          {checks.length === 0 ? (
            <p className="text-muted-foreground text-sm">No service checks configured</p>
          ) : (
            <div className="space-y-3">
              {checks.slice(0, 5).map((check) => (
                <div
                  key={check.id}
                  className="flex items-center justify-between py-2 border-b border-border last:border-0"
                >
                  <div>
                    <p className="font-medium text-foreground">{check.name}</p>
                    <p className="text-sm text-muted-foreground">
                      {check.check_type} • {check.target}
                    </p>
                  </div>
                  <span
                    className={`px-2 py-1 rounded-sm text-xs font-medium ${
                      check.enabled
                        ? 'bg-badge-success-bg text-badge-success-fg'
                        : 'bg-badge-neutral-bg text-badge-neutral-fg'
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
        <div className="bg-card rounded-sm shadow-sm border border-border p-6">
          <h2 className="text-lg font-semibold text-foreground mb-4">Device Status Distribution</h2>
          {deviceStatusData.length === 0 ? (
            <p className="text-muted-foreground text-sm text-center py-8">No devices to display</p>
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
                    backgroundColor: 'hsl(var(--chart-tooltip-bg))',
                    border: 'none',
                    borderRadius: '8px',
                    color: 'hsl(var(--chart-tooltip-fg))',
                  }}
                />
              </PieChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Poll Success Rate */}
        <div className="bg-card rounded-sm shadow-sm border border-border p-6">
          <h2 className="text-lg font-semibold text-foreground mb-4">Poll Success Rate (Last Hour)</h2>
          <ResponsiveContainer width="100%" height={250}>
            <LineChart data={pollData}>
              <XAxis dataKey="time" stroke="hsl(var(--chart-axis))" fontSize={12} />
              <YAxis stroke="hsl(var(--chart-axis))" fontSize={12} />
              <Tooltip
                contentStyle={{
                  backgroundColor: 'hsl(var(--chart-tooltip-bg))',
                  border: 'none',
                  borderRadius: '8px',
                  color: 'hsl(var(--chart-tooltip-fg))',
                }}
              />
              <Legend />
              <Line type="monotone" dataKey="success" stroke="hsl(var(--success))" strokeWidth={2} name="Success" />
              <Line type="monotone" dataKey="failed" stroke="hsl(var(--destructive))" strokeWidth={2} name="Failed" />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Device Uptime Chart */}
      <div className="bg-card rounded-sm shadow-sm border border-border p-6 mt-6">
        <h2 className="text-lg font-semibold text-foreground mb-4">Device Uptime (Last 250 Polls)</h2>
        {pollHistoryLoading || pollHistory.length === 0 ? (
          <p className="text-muted-foreground text-sm text-center py-8">No poll history available</p>
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
                  <XAxis dataKey="name" stroke="hsl(var(--chart-axis))" fontSize={12} angle={-30} textAnchor="end" height={60} />
                  <YAxis stroke="hsl(var(--chart-axis))" fontSize={12} domain={[0, 100]} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: 'hsl(var(--chart-tooltip-bg))',
                      border: 'none',
                      borderRadius: '8px',
                      color: 'hsl(var(--chart-tooltip-fg))',
                    }}
                  />
                  <Bar dataKey="uptime" fill="hsl(var(--success))" name="Uptime %" />
                </BarChart>
              </ResponsiveContainer>
            );
          })()
        )}
      </div>

      {/* Recent Topology Changes */}
      <div className="bg-card rounded-sm shadow-sm border border-border p-6 mt-6">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-lg font-semibold text-foreground flex items-center space-x-2">
            <History className="h-5 w-5 text-info" />
            <span>Recent Topology Changes</span>
          </h2>
          <Link
            to="/topology/history"
            className="text-sm text-foreground hover:text-foreground dark:hover:text-foreground"
          >
            View all →
          </Link>
        </div>
        {topologyEventsLoading || topologyEvents.length === 0 ? (
          <p className="text-muted-foreground text-sm text-center py-8">No topology changes recorded</p>
        ) : (
          <div className="space-y-2">
            {topologyEvents.slice(0, 10).map((event) => (
              <div
                key={event.id}
                className="flex items-center justify-between py-2 border-b border-border last:border-0"
              >
                <div className="flex items-center space-x-3">
                    <span
                    className={`inline-flex px-2 py-0.5 text-xs rounded-sm font-medium ${
                      event.event_type === 'node_added'
                        ? 'bg-badge-success-bg text-badge-success-fg'
                        : event.event_type === 'node_removed'
                        ? 'bg-badge-destructive-bg text-badge-destructive-fg'
                        : event.event_type === 'link_added'
                        ? 'bg-badge-info-bg text-badge-info-fg'
                        : event.event_type === 'link_removed'
                        ? 'bg-badge-destructive-bg text-badge-destructive-fg'
                        : 'bg-badge-neutral-bg text-badge-neutral-fg'
                    }`}
                  >
                    {event.event_type}
                  </span>
                  <span className="text-sm text-foreground">
                    {event.node_id || event.link_id || 'Topology'}
                  </span>
                </div>
                <span className="text-xs text-muted-foreground">
                  {new Date(event.recorded_at).toLocaleString()}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

        <div className="bg-card rounded-sm shadow-sm border border-border p-6 mt-6">
          <h2 className="text-lg font-semibold text-foreground mb-4">Topology Overview</h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="text-center p-4 bg-surface-subtle rounded-sm">
              <p className="text-2xl font-bold text-foreground">{topology.nodes.length}</p>
              <p className="text-sm text-muted-foreground mt-1">Total Nodes</p>
            </div>
            <div className="text-center p-4 bg-surface-subtle rounded-sm">
              <p className="text-2xl font-bold text-cyan-600 dark:text-cyan-400">{topology.links.length}</p>
              <p className="text-sm text-muted-foreground mt-1">Active Links</p>
            </div>
            <div className="text-center p-4 bg-surface-subtle rounded-sm">
              <p className="text-2xl font-bold text-emerald-600 dark:text-emerald-400">
                {topology.nodes.filter((n) => n.status === 'online').length}
              </p>
              <p className="text-sm text-muted-foreground mt-1">Online Nodes</p>
            </div>
            <div className="text-center p-4 bg-surface-subtle rounded-sm">
              <p className="text-2xl font-bold text-info">
                {topology.links.filter((l) => l.status === 'active').length}
              </p>
              <p className="text-sm text-muted-foreground mt-1">Active Connections</p>
            </div>
          </div>
        </div>
    </div>
  );
}

export default Dashboard;
