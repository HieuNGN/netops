import { Activity, Server, Network, CheckCircle, AlertCircle } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useTopology } from '../hooks/useTopology';
import { useDevices } from '../hooks/useDevices';
import { useChecks } from '../hooks/useChecks';

function StatCard({ title, value, subtext, icon: Icon, color }: any) {
  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium text-gray-600 dark:text-gray-400">{title}</p>
          <p className="text-3xl font-bold text-gray-900 dark:text-white mt-2">{value}</p>
          {subtext && <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">{subtext}</p>}
        </div>
        <div className={`p-3 rounded-lg ${color}`}>
          <Icon className="h-6 w-6 text-white" />
        </div>
      </div>
    </div>
  );
}

export function Dashboard() {
  const { topology } = useTopology();
  const { devices } = useDevices();
  const { checks } = useChecks();

  const deviceStats = {
    online: devices.filter((d) => d.status === 'online').length,
    offline: devices.filter((d) => d.status === 'offline').length,
    unknown: devices.filter((d) => d.status === 'unknown').length,
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Dashboard</h1>
        <p className="text-gray-600 dark:text-gray-400 mt-1">Network overview and health status</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        <StatCard
          title="Total Devices"
          value={devices.length}
          subtext={`${deviceStats.online} online, ${deviceStats.offline} offline`}
          icon={Server}
          color="bg-blue-500"
        />
        <StatCard
          title="Network Nodes"
          value={topology.nodes.length}
          subtext={`${topology.links.length} active links`}
          icon={Network}
          color="bg-purple-500"
        />
        <StatCard
          title="Service Checks"
          value={checks.length}
          subtext="Active monitoring"
          icon={Activity}
          color="bg-green-500"
        />
        <StatCard
          title="System Status"
          value={deviceStats.offline > 0 ? 'Issues' : 'Healthy'}
          subtext={deviceStats.offline > 0 ? `${deviceStats.offline} devices offline` : 'All systems operational'}
          icon={deviceStats.offline > 0 ? AlertCircle : CheckCircle}
          color={deviceStats.offline > 0 ? 'bg-red-500' : 'bg-green-500'}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Recent Devices */}
        <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Devices</h2>
            <Link to="/devices" className="text-sm text-purple-600 dark:text-purple-400 hover:text-purple-700 dark:hover:text-purple-300">
              View all →
            </Link>
          </div>
          {devices.length === 0 ? (
            <p className="text-gray-500 dark:text-gray-400 text-sm">No devices configured</p>
          ) : (
            <div className="space-y-3">
              {devices.slice(0, 5).map((device) => (
                <div
                  key={device.id}
                  className="flex items-center justify-between py-2 border-b border-gray-100 dark:border-gray-700 last:border-0"
                >
                  <div>
                    <p className="font-medium text-gray-900 dark:text-white">{device.name || device.ip_address}</p>
                    <p className="text-sm text-gray-500 dark:text-gray-400">{device.ip_address}</p>
                  </div>
                  <span
                    className={`px-2 py-1 rounded-full text-xs font-medium ${
                      device.status === 'online'
                        ? 'bg-green-100 text-green-700'
                        : device.status === 'offline'
                        ? 'bg-red-100 text-red-700'
                        : 'bg-gray-100 text-gray-700'
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
        <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Service Checks</h2>
            <Link to="/checks" className="text-sm text-purple-600 dark:text-purple-400 hover:text-purple-700 dark:hover:text-purple-300">
              View all →
            </Link>
          </div>
          {checks.length === 0 ? (
            <p className="text-gray-500 dark:text-gray-400 text-sm">No service checks configured</p>
          ) : (
            <div className="space-y-3">
              {checks.slice(0, 5).map((check) => (
                <div
                  key={check.id}
                  className="flex items-center justify-between py-2 border-b border-gray-100 dark:border-gray-700 last:border-0"
                >
                  <div>
                    <p className="font-medium text-gray-900 dark:text-white">{check.name}</p>
                    <p className="text-sm text-gray-500 dark:text-gray-400">
                      {check.check_type} • {check.target}
                    </p>
                  </div>
                  <span
                    className={`px-2 py-1 rounded-full text-xs font-medium ${
                      check.enabled
                        ? 'bg-green-100 text-green-700'
                        : 'bg-gray-100 text-gray-700'
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
  );
}
