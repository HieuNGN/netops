import { useMemo, useState } from 'react';
import { Activity, Server, Network, CheckCircle, AlertCircle, ArrowUpCircle, ArrowDownCircle, Bell, Check, X, History, Settings, RefreshCcw } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useTopology } from '../hooks/useTopology';
import { useDevices } from '../hooks/useDevices';
import { useChecks } from '../hooks/useChecks';
import { useActiveAlerts } from '../hooks/useActiveAlerts';
import { usePollHistory } from '../hooks/usePollHistory';
import { useTopologyHistory } from '../hooks/useTopologyHistory';
import { NetworkPicker } from '../components/NetworkPicker';
import { NetworksConsole } from '../components/NetworksConsole';
import { LineChart, Line, PieChart, Pie, Cell, ResponsiveContainer, XAxis, YAxis, Tooltip, BarChart, Bar } from 'recharts';

type Trend = { pct: number; up: boolean };

function StatCard({
  title,
  value,
  subtext,
  icon: Icon,
  accentClass,
  trend,
  loading,
  to,
}: {
  title: string;
  value: number | string;
  subtext?: string;
  icon: React.ComponentType<{ className?: string }>;
  accentClass: string;
  trend?: Trend;
  loading?: boolean;
  to?: string;
}) {
  const inner = (
    <div className="flex items-start justify-between gap-3">
      <div className="min-w-0 flex-1">
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{title}</p>
        {loading ? (
          <div className="h-9 w-20 mt-2 bg-muted animate-pulse rounded-sm" />
        ) : (
          <p className="text-3xl font-semibold text-foreground mt-1.5 tabular-nums">{value}</p>
        )}
        {subtext && <p className="text-xs text-muted-foreground mt-1.5">{subtext}</p>}
        {trend && !loading && (
          <div className={`flex items-center gap-1 mt-2 text-xs font-medium ${trend.up ? 'text-cisco-green' : 'text-thinkpad-red'}`}>
            {trend.up ? <ArrowUpCircle className="h-3.5 w-3.5" /> : <ArrowDownCircle className="h-3.5 w-3.5" />}
            <span className="tabular-nums">{Math.abs(trend.pct)}%</span>
            <span className="text-muted-foreground font-normal">vs prior period</span>
          </div>
        )}
      </div>
      <div className={`shrink-0 p-2.5 rounded-sm ${accentClass}`}>
        <Icon className="h-5 w-5 text-white" />
      </div>
    </div>
  );
  if (to) {
    return (
      <Link to={to} className="group relative bg-card border border-border rounded-sm p-5 transition-colors hover:border-foreground/20 cursor-pointer block">
        {inner}
      </Link>
    );
  }
  return (
    <div className="group relative bg-card border border-border rounded-sm p-5 transition-colors hover:border-foreground/20">
      {inner}
    </div>
  );
}

function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`bg-muted animate-pulse rounded-sm ${className}`} />;
}

function DeviceStatusDot({ status }: { status: string }) {
  const map: Record<string, string> = {
    online: 'bg-cisco-green',
    offline: 'bg-thinkpad-red',
    unknown: 'bg-cisco-blue',
    discovered: 'bg-ibm-yellow',
  };
  return <span className={`inline-block h-2 w-2 rounded-full ${map[status] || 'bg-muted-foreground'}`} />;
}

function StatusPill({ status }: { status: string }) {
  const cls: Record<string, string> = {
    online: 'bg-badge-success-bg text-badge-success-fg',
    offline: 'bg-badge-destructive-bg text-badge-destructive-fg',
    unknown: 'bg-badge-info-bg text-badge-info-fg',
    discovered: 'bg-badge-warning-bg text-badge-warning-fg',
  };
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 text-xs font-medium rounded-sm ${cls[status] || 'bg-badge-neutral-bg text-badge-neutral-fg'}`}>
      <DeviceStatusDot status={status} />
      {status}
    </span>
  );
}

function relativeTime(ts: string | number | null | undefined): string {
  if (!ts) return 'never';
  const t = typeof ts === 'string' ? new Date(ts).getTime() : ts * 1000;
  const diff = Date.now() - t;
  const s = Math.floor(diff / 1000);
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  return `${d}d ago`;
}

export function Dashboard() {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const { topology } = useTopology();
  const { devices, isLoading: devicesLoading } = useDevices();
  const { checks, isLoading: checksLoading } = useChecks();
  const { alerts: activeAlerts, acknowledge, resolve } = useActiveAlerts();
  const { history: pollHistory, isLoading: pollHistoryLoading } = usePollHistory(250);
  const { events: topologyEvents, isLoading: topologyEventsLoading } = useTopologyHistory({ limit: 20 });

  const deviceStats = useMemo(() => ({
    online: devices.filter((d) => d.status === 'online').length,
    offline: devices.filter((d) => d.status === 'offline').length,
    unknown: devices.filter((d) => d.status === 'unknown').length,
    discovered: devices.filter((d) => d.status === 'discovered').length,
  }), [devices]);

  const totalDevices = devices.length;
  const systemHealthy = deviceStats.offline === 0 && deviceStats.unknown === 0 && totalDevices > 0;

  // Real poll success rate by 5-min bucket over the last hour
  const pollSuccessSeries = useMemo(() => {
    if (!pollHistory.length) return [];
    const BUCKET_MS = 5 * 60_000;
    const HOUR_MS = 60 * 60_000;
    const now = Date.now();
    const buckets: { ts: number; label: string; success: number; failed: number }[] = [];
    for (let i = 11; i >= 0; i--) {
      const ts = now - i * BUCKET_MS;
      buckets.push({
        ts,
        label: new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        success: 0,
        failed: 0,
      });
    }
    for (const entry of pollHistory) {
      const t = entry.polled_at ? new Date(entry.polled_at).getTime() : 0;
      if (!t || now - t > HOUR_MS) continue;
      const idx = Math.floor((t - (now - 12 * BUCKET_MS)) / BUCKET_MS);
      if (idx < 0 || idx >= buckets.length) continue;
      if (entry.status === 'online' || entry.status === 'success') buckets[idx].success += 1;
      else if (entry.status === 'offline' || entry.status === 'failed') buckets[idx].failed += 1;
    }
    return buckets;
  }, [pollHistory]);

  // Real uptime % per device over the last 250 polls
  const uptimeData = useMemo(() => {
    if (!pollHistory.length) return [];
    const acc: Record<string, { name: string; total: number; online: number }> = {};
    for (const entry of pollHistory) {
      const id = entry.device_id;
      if (!acc[id]) {
        acc[id] = { name: entry.name || entry.ip_address || id, total: 0, online: 0 };
      }
      acc[id].total += 1;
      if (entry.status === 'online' || entry.status === 'success') acc[id].online += 1;
    }
    return Object.values(acc)
      .map((d) => ({ name: d.name, uptime: Math.round((d.online / d.total) * 100) }))
      .sort((a, b) => a.name.localeCompare(b.name));
  }, [pollHistory]);

  const overallUptime = useMemo(() => {
    if (!uptimeData.length) return 0;
    const total = uptimeData.reduce((s, d) => s + d.uptime, 0);
    return Math.round(total / uptimeData.length);
  }, [uptimeData]);

  const deviceStatusData = [
    { name: 'Online', value: deviceStats.online, status: 'online' },
    { name: 'Offline', value: deviceStats.offline, status: 'offline' },
    { name: 'Unknown', value: deviceStats.unknown, status: 'unknown' },
    { name: 'Discovered', value: deviceStats.discovered, status: 'discovered' },
  ].filter((d) => d.value > 0);

  const fillForStatus = (status: string) => {
    if (status === 'online') return 'hsl(var(--cisco-green))';
    if (status === 'offline') return 'hsl(var(--thinkpad-red))';
    if (status === 'discovered') return 'hsl(var(--ibm-yellow))';
    return 'hsl(var(--cisco-blue))';
  };

  const lastTopologyChange = topologyEvents[0];
  const lastPoll = pollHistory[0]?.polled_at;

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="mb-8 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-foreground">Dashboard</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Network overview &middot; last poll {relativeTime(lastPoll)}
          </p>
        </div>
        <Link
          to="/topology"
          className="inline-flex items-center gap-1.5 text-sm px-3 py-1.5 bg-ibm-blue text-white rounded-sm hover:bg-ibm-blue-hover transition-colors"
        >
          <Activity className="h-3.5 w-3.5" />
          Open topology
        </Link>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <StatCard
          title="Devices"
          value={totalDevices}
          subtext={`${deviceStats.online} online · ${deviceStats.offline} offline`}
          icon={Server}
          accentClass="bg-cisco-blue"
          loading={devicesLoading}
          to="/devices"
        />
        <StatCard
          title="Topology"
          value={topology.nodes.length}
          subtext={`${topology.links.length} links · ${deviceStats.online} reachable`}
          icon={Network}
          accentClass="bg-ibm-purple"
          to="/topology"
        />
        <StatCard
          title="Service Checks"
          value={checks.length}
          subtext={`${checks.filter((c) => c.enabled).length} enabled`}
          icon={Activity}
          accentClass="bg-cisco-green"
          loading={checksLoading}
          to="/checks"
        />
        <StatCard
          title="System Status"
          value={totalDevices === 0 ? 'No data' : systemHealthy ? 'Healthy' : 'Degraded'}
          subtext={
            totalDevices === 0
              ? 'Add devices to begin monitoring'
              : systemHealthy
                ? 'All systems operational'
                : `${deviceStats.offline + deviceStats.unknown} device${deviceStats.offline + deviceStats.unknown === 1 ? '' : 's'} need attention`
          }
          icon={systemHealthy ? CheckCircle : AlertCircle}
          accentClass={systemHealthy ? 'bg-cisco-green' : 'bg-thinkpad-red'}
          to="/devices"
        />
      </div>

      {activeAlerts.length > 0 && (
        <div className="mb-6 bg-card border border-border rounded-sm overflow-hidden">
          <div className="flex justify-between items-center px-5 py-3 border-b border-border bg-surface-subtle">
            <h2 className="text-sm font-semibold text-foreground flex items-center gap-2">
              <Bell className="h-4 w-4 text-thinkpad-red" />
              Active Alerts
              <span className="px-1.5 py-0.5 bg-thinkpad-red text-white text-xs rounded-sm font-medium tabular-nums">
                {activeAlerts.length}
              </span>
            </h2>
            <Link to="/alerts" className="text-xs text-info hover:underline">
              View all &rarr;
            </Link>
          </div>
          <div className="divide-y divide-border">
            {activeAlerts.map((alert) => (
              <div
                key={alert.key}
                className={`flex items-center justify-between px-5 py-3 border-l-4 ${
                  alert.status === 'firing'
                    ? 'border-l-thinkpad-red bg-badge-destructive-bg/30'
                    : 'border-l-ibm-yellow bg-badge-warning-bg/30'
                }`}
              >
                <div className="flex items-start gap-3 min-w-0 flex-1">
                  <span
                    className={`shrink-0 inline-flex px-2 py-0.5 text-xs rounded-sm font-medium ${
                      alert.severity === 'critical'
                        ? 'bg-thinkpad-red text-white'
                        : alert.severity === 'warning'
                          ? 'bg-ibm-yellow text-black'
                          : 'bg-secondary text-foreground dark:bg-muted dark:text-muted-foreground'
                    }`}
                  >
                    {alert.severity}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-foreground truncate">{alert.title}</p>
                    <p className="text-xs text-muted-foreground truncate">{alert.message}</p>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      {alert.status === 'acknowledged' && (
                        <span className="text-ibm-yellow font-medium">Acknowledged &middot; </span>
                      )}
                      Fired {new Date(alert.fired_at * 1000).toLocaleTimeString()}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-1 shrink-0 ml-3">
                  {alert.status === 'firing' && (
                    <button
                      onClick={() => acknowledge(alert.key)}
                      className="p-1.5 text-ibm-cyan hover:bg-surface-hover rounded-sm"
                      title="Acknowledge"
                    >
                      <Check className="h-4 w-4" />
                    </button>
                  )}
                  <button
                    onClick={() => resolve(alert.key)}
                    className="p-1.5 text-cisco-green hover:bg-badge-success-bg rounded-sm"
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

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
        <div className="lg:col-span-2 bg-card border border-border rounded-sm">
          <div className="flex justify-between items-center px-5 py-3 border-b border-border">
            <h2 className="text-sm font-semibold text-foreground flex items-center gap-2">
              <Activity className="h-4 w-4 text-cisco-teal" />
              Poll Success Rate
              <span className="text-xs text-muted-foreground font-normal">(last hour, 5-min buckets)</span>
            </h2>
            <span className="text-xs text-muted-foreground tabular-nums">
              {overallUptime}% avg uptime
            </span>
          </div>
          <div className="p-5">
            {pollHistoryLoading ? (
              <Skeleton className="h-[220px] w-full" />
            ) : pollSuccessSeries.every((b) => b.success === 0 && b.failed === 0) ? (
              <div className="h-[220px] flex items-center justify-center text-sm text-muted-foreground">
                No poll history recorded yet
              </div>
            ) : (
              <ResponsiveContainer width="100%" height={220}>
                <LineChart data={pollSuccessSeries} margin={{ top: 5, right: 5, left: -10, bottom: 0 }}>
                  <XAxis dataKey="label" stroke="hsl(var(--chart-axis))" fontSize={11} tickLine={false} />
                  <YAxis stroke="hsl(var(--chart-axis))" fontSize={11} tickLine={false} axisLine={false} allowDecimals={false} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: 'hsl(var(--chart-tooltip-bg))',
                      border: '1px solid hsl(var(--border))',
                      borderRadius: '2px',
                      color: 'hsl(var(--chart-tooltip-fg))',
                      fontSize: 12,
                    }}
                  />
                  <Line type="monotone" dataKey="success" stroke="hsl(var(--cisco-green))" strokeWidth={2} dot={false} name="Success" />
                  <Line type="monotone" dataKey="failed" stroke="hsl(var(--thinkpad-red))" strokeWidth={2} dot={false} name="Failed" />
                </LineChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>

        <div className="bg-card border border-border rounded-sm">
          <div className="flex justify-between items-center px-5 py-3 border-b border-border">
            <h2 className="text-sm font-semibold text-foreground">Device Status</h2>
            <Link to="/devices" className="text-xs text-info hover:underline">View all &rarr;</Link>
          </div>
          <div className="p-5">
            {deviceStatusData.length === 0 ? (
              <div className="h-[220px] flex items-center justify-center text-sm text-muted-foreground">
                No devices yet
              </div>
            ) : (
              <div className="flex items-center gap-4">
                <ResponsiveContainer width={140} height={140}>
                  <PieChart>
                    <Pie
                      data={deviceStatusData}
                      cx="50%"
                      cy="50%"
                      innerRadius={42}
                      outerRadius={66}
                      paddingAngle={2}
                      dataKey="value"
                      stroke="hsl(var(--card))"
                      strokeWidth={2}
                    >
                      {deviceStatusData.map((entry, i) => (
                        <Cell key={i} fill={fillForStatus(entry.status)} />
                      ))}
                    </Pie>
                  </PieChart>
                </ResponsiveContainer>
                <div className="flex-1 space-y-1.5 min-w-0">
                  {deviceStatusData.map((d) => (
                    <div key={d.name} className="flex items-center justify-between text-xs">
                      <div className="flex items-center gap-1.5 min-w-0">
                        <span
                          className="inline-block h-2 w-2 rounded-full shrink-0"
                          style={{ backgroundColor: fillForStatus(d.status) }}
                        />
                        <span className="text-foreground">{d.name}</span>
                      </div>
                      <span className="text-muted-foreground tabular-nums font-medium">{d.value}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
        <div className="bg-card border border-border rounded-sm">
          <div className="flex justify-between items-center px-5 py-3 border-b border-border">
            <h2 className="text-sm font-semibold text-foreground">Networks</h2>
          </div>
          <div className="p-5 space-y-3">
            <NetworkPicker />
            <div className="pt-2 border-t border-border">
              <button
                onClick={() => setDrawerOpen(true)}
                className="w-full inline-flex items-center justify-center gap-1.5 text-sm px-3 py-1.5 bg-ibm-blue text-white rounded-sm hover:bg-ibm-blue-hover transition-colors"
              >
                <Settings className="h-3.5 w-3.5" />
                Manage Networks
              </button>
            </div>
          </div>
        </div>

        <div className="bg-card border border-border rounded-sm">
          <div className="flex justify-between items-center px-5 py-3 border-b border-border">
            <h2 className="text-sm font-semibold text-foreground">Recent Devices</h2>
            <Link to="/devices" className="text-xs text-info hover:underline">View all &rarr;</Link>
          </div>
          <div className="p-2">
            {devicesLoading ? (
              <div className="space-y-2 p-3">
                {[1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-10 w-full" />)}
              </div>
            ) : devices.length === 0 ? (
              <div className="px-5 py-8 text-sm text-muted-foreground text-center">
                No devices yet. <Link to="/devices" className="text-info hover:underline">Add one</Link>.
              </div>
            ) : (
              <div className="divide-y divide-border">
                {devices.slice(0, 5).map((device) => (
                  <Link
                    key={device.id}
                    to="/devices"
                    className="flex items-center justify-between px-3 py-2.5 hover:bg-surface-hover transition-colors"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium text-foreground truncate">
                        {device.name || device.ip_address}
                      </p>
                      <p className="text-xs text-muted-foreground font-mono truncate">
                        {device.ip_address} &middot; polled {relativeTime(device.last_polled)}
                      </p>
                    </div>
                    <StatusPill status={device.status} />
                  </Link>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="bg-card border border-border rounded-sm">
          <div className="flex justify-between items-center px-5 py-3 border-b border-border">
            <h2 className="text-sm font-semibold text-foreground">Service Checks</h2>
            <Link to="/checks" className="text-xs text-info hover:underline">View all &rarr;</Link>
          </div>
          <div className="p-2">
            {checksLoading ? (
              <div className="space-y-2 p-3">
                {[1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-10 w-full" />)}
              </div>
            ) : checks.length === 0 ? (
              <div className="px-5 py-8 text-sm text-muted-foreground text-center">
                No service checks yet. <Link to="/checks" className="text-info hover:underline">Add one</Link>.
              </div>
            ) : (
              <div className="divide-y divide-border">
                {checks.slice(0, 5).map((check) => (
                  <div key={check.id} className="flex items-center justify-between px-3 py-2.5">
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium text-foreground truncate">{check.name}</p>
                      <p className="text-xs text-muted-foreground font-mono truncate">
                        {check.check_type} &middot; {check.target}
                      </p>
                    </div>
                    <span
                      className={`shrink-0 px-2 py-0.5 text-xs rounded-sm font-medium ${
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
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
        <div className="lg:col-span-2 bg-card border border-border rounded-sm">
          <div className="flex justify-between items-center px-5 py-3 border-b border-border">
            <h2 className="text-sm font-semibold text-foreground">Device Uptime</h2>
            <span className="text-xs text-muted-foreground">last 250 polls</span>
          </div>
          <div className="p-5">
            {pollHistoryLoading ? (
              <Skeleton className="h-[220px] w-full" />
            ) : uptimeData.length === 0 ? (
              <div className="h-[220px] flex items-center justify-center text-sm text-muted-foreground">
                No poll history available
              </div>
            ) : (
              <ResponsiveContainer width="100%" height={Math.max(180, uptimeData.length * 28)}>
                <BarChart data={uptimeData} layout="vertical" margin={{ top: 0, right: 16, left: 0, bottom: 0 }}>
                  <XAxis type="number" stroke="hsl(var(--chart-axis))" fontSize={11} domain={[0, 100]} tickFormatter={(v) => `${v}%`} />
                  <YAxis dataKey="name" type="category" stroke="hsl(var(--chart-axis))" fontSize={11} width={140} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: 'hsl(var(--chart-tooltip-bg))',
                      border: '1px solid hsl(var(--border))',
                      borderRadius: '2px',
                      color: 'hsl(var(--chart-tooltip-fg))',
                      fontSize: 12,
                    }}
                    formatter={(v) => [`${v}%`, 'Uptime']}
                  />
                  <Bar
                    dataKey="uptime"
                    radius={[0, 2, 2, 0]}
                    background={{ fill: 'hsl(var(--muted))', radius: 2 }}
                  >
                    {uptimeData.map((d, i) => (
                      <Cell
                        key={i}
                        fill={d.uptime >= 99 ? 'hsl(var(--cisco-green))' : d.uptime >= 90 ? 'hsl(var(--ibm-yellow))' : 'hsl(var(--thinkpad-red))'}
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>

        <div className="bg-card border border-border rounded-sm">
          <div className="flex justify-between items-center px-5 py-3 border-b border-border">
            <h2 className="text-sm font-semibold text-foreground flex items-center gap-2">
              <History className="h-4 w-4 text-cisco-teal" />
              Recent Topology
            </h2>
            <Link to="/topology/history" className="text-xs text-info hover:underline">View all &rarr;</Link>
          </div>
          <div className="p-2">
            {topologyEventsLoading ? (
              <div className="space-y-2 p-3">
                {[1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-8 w-full" />)}
              </div>
            ) : topologyEvents.length === 0 ? (
              <div className="px-5 py-8 text-sm text-muted-foreground text-center">
                No topology changes recorded
              </div>
            ) : (
              <div className="divide-y divide-border">
                {topologyEvents.slice(0, 6).map((event) => (
                  <div key={event.id} className="flex items-center justify-between px-3 py-2 text-xs">
                    <div className="flex items-center gap-2 min-w-0 flex-1">
                      <span
                        className={`shrink-0 inline-flex px-1.5 py-0.5 text-[10px] uppercase tracking-wide rounded-sm font-medium ${
                          event.event_type === 'node_added' || event.event_type === 'link_added'
                            ? 'bg-badge-success-bg text-badge-success-fg'
                            : event.event_type === 'node_removed' || event.event_type === 'link_removed'
                              ? 'bg-badge-destructive-bg text-badge-destructive-fg'
                              : 'bg-badge-info-bg text-badge-info-fg'
                        }`}
                      >
                        {event.event_type.replace(/_/g, ' ')}
                      </span>
                      <span className="text-foreground truncate font-mono">
                        {event.node_id || event.link_id || 'topology'}
                      </span>
                    </div>
                    <span className="text-muted-foreground shrink-0 ml-2">
                      {relativeTime(event.recorded_at)}
                    </span>
                  </div>
                ))}
                {lastTopologyChange && (
                  <div className="px-3 py-2 text-[10px] text-muted-foreground flex items-center gap-1">
                    <RefreshCcw className="h-2.5 w-2.5" />
                    last change {relativeTime(lastTopologyChange.recorded_at)}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      <NetworksConsole open={drawerOpen} onClose={() => setDrawerOpen(false)} />
    </div>
  );
}

export default Dashboard;
