import { useState } from 'react';
import { Plus, Search, Trash2, ScanLine, X } from 'lucide-react';
import { useDevices } from '../hooks/useDevices';
import { useToast } from '../components/ui';

export function Devices() {
  const { devices, isLoading, createDevice, deleteDevice, discoverNetwork, isDiscovering } = useDevices();
  const toast = useToast();
  const [showAddForm, setShowAddForm] = useState(false);
  const [showScanModal, setShowScanModal] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [newDevice, setNewDevice] = useState({
    name: '',
    ip_address: '',
    community: 'public',
  });
  const [scanConfig, setScanConfig] = useState({
    network_range: '192.168.1.0/24',
    community: 'public',
    method: 'all',
  });

  const filteredDevices = devices.filter(
    (d) =>
      d.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      d.ip_address.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await createDevice(newDevice);
      toast.success('Device added successfully', `${newDevice.name || newDevice.ip_address}`);
      setNewDevice({ name: '', ip_address: '', community: 'public' });
      setShowAddForm(false);
    } catch (error) {
      toast.error('Failed to create device', 'Error');
    }
  };

  const handleDelete = async (id: string) => {
    if (confirm('Are you sure you want to delete this device?')) {
      try {
        await deleteDevice(id);
        toast.success('Device deleted successfully');
      } catch (error) {
        toast.error('Failed to delete device', 'Error');
      }
    }
  };

  const handleDiscover = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const result = await discoverNetwork({
        network_range: scanConfig.network_range,
        community: scanConfig.community || 'public',
        method: scanConfig.method,
      });
      toast.success(
        'Network scan complete',
        `Found ${result.found} devices, added ${result.added} new`
      );
      setShowScanModal(false);
    } catch (error) {
      toast.error('Network scan failed', 'Error');
    }
  };

  const statusBadge = (status: string) => {
    const styles: Record<string, string> = {
      online: 'bg-green-100 text-green-700',
      offline: 'bg-red-100 text-red-700',
      discovered: 'bg-blue-100 text-blue-700',
    };
    return styles[status] || 'bg-gray-100 text-gray-700';
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Devices</h1>
          <p className="text-gray-600 dark:text-gray-400 mt-1">Manage network devices for monitoring</p>
        </div>
        <div className="flex space-x-2">
          <button
            onClick={() => setShowScanModal(true)}
            className="flex items-center space-x-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
          >
            <ScanLine className="h-4 w-4" />
            <span>Scan Network</span>
          </button>
          <button
            onClick={() => setShowAddForm(true)}
            className="flex items-center space-x-2 px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700"
          >
            <Plus className="h-4 w-4" />
            <span>Add Device</span>
          </button>
        </div>
      </div>

      {/* Search */}
      <div className="mb-6">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-5 w-5 text-gray-400" />
          <input
            type="text"
            placeholder="Search by name or IP..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full pl-10 pr-4 py-2 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent"
          />
        </div>
      </div>

      {/* Add Device Form */}
      {showAddForm && (
        <div className="mb-6 bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Add New Device</h2>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Name (optional)
                </label>
                <input
                  type="text"
                  value={newDevice.name}
                  onChange={(e) => setNewDevice({ ...newDevice, name: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white rounded-lg focus:ring-2 focus:ring-purple-500"
                  placeholder="Router-1"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  IP Address *
                </label>
                <input
                  type="text"
                  value={newDevice.ip_address}
                  onChange={(e) => setNewDevice({ ...newDevice, ip_address: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white rounded-lg focus:ring-2 focus:ring-purple-500"
                  placeholder="192.168.1.1"
                  required
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  SNMP Community
                </label>
                <input
                  type="text"
                  value={newDevice.community}
                  onChange={(e) => setNewDevice({ ...newDevice, community: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white rounded-lg focus:ring-2 focus:ring-purple-500"
                  placeholder="public"
                />
              </div>
            </div>
            <div className="flex justify-end space-x-2">
              <button
                type="button"
                onClick={() => setShowAddForm(false)}
                className="px-4 py-2 text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600"
              >
                Cancel
              </button>
              <button
                type="submit"
                className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700"
              >
                Add Device
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Scan Network Modal */}
      {showScanModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50">
          <div className="bg-white dark:bg-gray-800 rounded-xl shadow-lg border border-gray-200 dark:border-gray-700 p-6 w-full max-w-md mx-4">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Scan Network</h2>
              <button
                onClick={() => setShowScanModal(false)}
                className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <form onSubmit={handleDiscover} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Network Range
                </label>
                <input
                  type="text"
                  value={scanConfig.network_range}
                  onChange={(e) => setScanConfig({ ...scanConfig, network_range: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white rounded-lg focus:ring-2 focus:ring-blue-500"
                  placeholder="192.168.1.0/24"
                  required
                />
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                  CIDR notation, e.g. 192.168.1.0/24
                </p>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Discovery Method
                </label>
                <select
                  value={scanConfig.method}
                  onChange={(e) => setScanConfig({ ...scanConfig, method: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white rounded-lg focus:ring-2 focus:ring-blue-500"
                >
                  <option value="all">All Methods (SNMP + Ping + Ports)</option>
                  <option value="snmp">SNMP Only</option>
                  <option value="ping">Ping + Ports</option>
                  <option value="port">Port Scan Only</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  SNMP Community
                </label>
                <input
                  type="text"
                  value={scanConfig.community}
                  onChange={(e) => setScanConfig({ ...scanConfig, community: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white rounded-lg focus:ring-2 focus:ring-blue-500"
                  placeholder="public"
                />
              </div>
              <div className="flex justify-end space-x-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowScanModal(false)}
                  className="px-4 py-2 text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isDiscovering}
                  className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {isDiscovering ? 'Scanning...' : 'Start Scan'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Devices Table */}
      <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 overflow-hidden">
        <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
          <thead className="bg-gray-50 dark:bg-gray-900">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                Name
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                IP Address
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                Community
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                Status
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                Method
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                Last Polled
              </th>
              <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
            {isLoading ? (
              <tr>
                <td colSpan={7} className="px-6 py-8 text-center text-gray-500 dark:text-gray-400">
                  Loading devices...
                </td>
              </tr>
            ) : filteredDevices.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-6 py-8 text-center text-gray-500 dark:text-gray-400">
                  {devices.length === 0
                    ? 'No devices configured. Add your first device or scan the network.'
                    : 'No devices match your search.'}
                </td>
              </tr>
            ) : (
              filteredDevices.map((device) => (
                <tr key={device.id} className="hover:bg-gray-50 dark:hover:bg-gray-700">
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="text-sm font-medium text-gray-900 dark:text-white">
                      {device.name || '-'}
                    </div>
                    {device.sys_descr && (
                      <div className="text-xs text-gray-500 dark:text-gray-400 truncate max-w-xs" title={device.sys_descr}>
                        {device.sys_descr}
                      </div>
                    )}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="text-sm text-gray-900 dark:text-white font-mono">{device.ip_address}</div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="text-sm text-gray-900 dark:text-white">{device.community}</div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span
                      className={`inline-flex px-2 py-1 rounded-full text-xs font-medium ${statusBadge(device.status)}`}
                    >
                      {device.status}
                    </span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span className="inline-flex px-2 py-1 rounded-full text-xs font-medium bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300">
                      {device.discovery_method || 'manual'}
                    </span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                    {device.last_polled || 'Never'}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                    <button
                      onClick={() => handleDelete(device.id)}
                      className="text-red-600 hover:text-red-900 dark:hover:text-red-400 ml-4"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
