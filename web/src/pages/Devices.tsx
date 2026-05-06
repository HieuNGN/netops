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
      online: 'bg-[#defbe6] text-[#24a148]',
      offline: 'bg-[#fff0f1] text-[#da1e28]',
      discovered: 'bg-[#e0e0e0] text-[#0f62fe]',
    };
    return styles[status] || 'bg-[#e0e0e0] text-[#161616]';
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-6 gap-4">
        <div>
          <h1 className="text-2xl font-bold text-[#161616] dark:text-white">Devices</h1>
          <p className="text-[#525252] dark:text-[#a8a8a8] mt-1">Manage network devices for monitoring</p>
        </div>
        <div className="flex space-x-2">
          <button
            onClick={() => setShowScanModal(true)}
            className="flex items-center space-x-2 px-4 py-2 bg-[#0f62fe] text-white rounded-sm hover:bg-[#0353e9]"
          >
            <ScanLine className="h-4 w-4" />
            <span>Scan Network</span>
          </button>
          <button
            onClick={() => setShowAddForm(true)}
            className="flex items-center space-x-2 px-4 py-2 bg-[#161616] text-white rounded-sm hover:bg-[#525252]"
          >
            <Plus className="h-4 w-4" />
            <span>Add Device</span>
          </button>
        </div>
      </div>

      {/* Search */}
      <div className="mb-6">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-5 w-5 text-[#a8a8a8]" />
          <input
            type="text"
            placeholder="Search by name or IP..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full pl-10 pr-4 py-2 border border-[#c6c6c6] dark:border-[#525252] bg-white dark:bg-[#262626] text-[#161616] dark:text-white rounded-sm focus:ring-1 focus:ring-[#da1e28] focus:border-transparent"
          />
        </div>
      </div>

      {/* Add Device Form */}
      {showAddForm && (
        <div className="mb-6 bg-white dark:bg-[#262626] rounded-sm shadow-sm border border-[#e0e0e0] dark:border-[#393939] p-6">
          <h2 className="text-lg font-semibold text-[#161616] dark:text-white mb-4">Add New Device</h2>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <label className="block text-sm font-medium text-[#161616] dark:text-[#a8a8a8] mb-1">
                  Name (optional)
                </label>
                <input
                  type="text"
                  value={newDevice.name}
                  onChange={(e) => setNewDevice({ ...newDevice, name: e.target.value })}
                  className="w-full px-3 py-2 border border-[#c6c6c6] dark:border-[#525252] bg-white dark:bg-[#262626] text-[#161616] dark:text-white rounded-sm focus:ring-1 focus:ring-[#da1e28]"
                  placeholder="Router-1"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-[#161616] dark:text-[#a8a8a8] mb-1">
                  IP Address *
                </label>
                <input
                  type="text"
                  value={newDevice.ip_address}
                  onChange={(e) => setNewDevice({ ...newDevice, ip_address: e.target.value })}
                  className="w-full px-3 py-2 border border-[#c6c6c6] dark:border-[#525252] bg-white dark:bg-[#262626] text-[#161616] dark:text-white rounded-sm focus:ring-1 focus:ring-[#da1e28]"
                  placeholder="192.168.1.1"
                  required
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-[#161616] dark:text-[#a8a8a8] mb-1">
                  SNMP Community
                </label>
                <input
                  type="text"
                  value={newDevice.community}
                  onChange={(e) => setNewDevice({ ...newDevice, community: e.target.value })}
                  className="w-full px-3 py-2 border border-[#c6c6c6] dark:border-[#525252] bg-white dark:bg-[#262626] text-[#161616] dark:text-white rounded-sm focus:ring-1 focus:ring-[#da1e28]"
                  placeholder="public"
                />
              </div>
            </div>
            <div className="flex justify-end space-x-2">
              <button
                type="button"
                onClick={() => setShowAddForm(false)}
                className="px-4 py-2 text-[#161616] dark:text-[#a8a8a8] bg-[#e0e0e0] dark:bg-[#262626] rounded-sm hover:bg-[#e0e0e0] dark:hover:bg-[#393939]"
              >
                Cancel
              </button>
              <button
                type="submit"
                className="px-4 py-2 bg-[#161616] text-white rounded-sm hover:bg-[#525252]"
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
          <div className="bg-white dark:bg-[#262626] rounded-sm shadow-lg border border-[#e0e0e0] dark:border-[#393939] p-6 w-full max-w-md mx-4">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-lg font-semibold text-[#161616] dark:text-white">Scan Network</h2>
              <button
                onClick={() => setShowScanModal(false)}
                className="text-[#a8a8a8] hover:text-[#525252] dark:hover:text-[#c6c6c6]"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <form onSubmit={handleDiscover} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-[#161616] dark:text-[#a8a8a8] mb-1">
                  Network Range
                </label>
                <input
                  type="text"
                  value={scanConfig.network_range}
                  onChange={(e) => setScanConfig({ ...scanConfig, network_range: e.target.value })}
                  className="w-full px-3 py-2 border border-[#c6c6c6] dark:border-[#525252] bg-white dark:bg-[#262626] text-[#161616] dark:text-white rounded-sm focus:ring-1 focus:ring-[#da1e28]"
                  placeholder="192.168.1.0/24"
                  required
                />
                <p className="text-xs text-[#525252] dark:text-[#a8a8a8] mt-1">
                  CIDR notation, e.g. 192.168.1.0/24
                </p>
              </div>
              <div>
                <label className="block text-sm font-medium text-[#161616] dark:text-[#a8a8a8] mb-1">
                  Discovery Method
                </label>
                <select
                  value={scanConfig.method}
                  onChange={(e) => setScanConfig({ ...scanConfig, method: e.target.value })}
                  className="w-full px-3 py-2 border border-[#c6c6c6] dark:border-[#525252] bg-white dark:bg-[#262626] text-[#161616] dark:text-white rounded-sm focus:ring-1 focus:ring-[#da1e28]"
                >
                  <option value="all">All Methods (SNMP + Ping + Ports)</option>
                  <option value="snmp">SNMP Only</option>
                  <option value="ping">Ping + Ports</option>
                  <option value="port">Port Scan Only</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-[#161616] dark:text-[#a8a8a8] mb-1">
                  SNMP Community
                </label>
                <input
                  type="text"
                  value={scanConfig.community}
                  onChange={(e) => setScanConfig({ ...scanConfig, community: e.target.value })}
                  className="w-full px-3 py-2 border border-[#c6c6c6] dark:border-[#525252] bg-white dark:bg-[#262626] text-[#161616] dark:text-white rounded-sm focus:ring-1 focus:ring-[#da1e28]"
                  placeholder="public"
                />
              </div>
              <div className="flex justify-end space-x-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowScanModal(false)}
                  className="px-4 py-2 text-[#161616] dark:text-[#a8a8a8] bg-[#e0e0e0] dark:bg-[#262626] rounded-sm hover:bg-[#e0e0e0] dark:hover:bg-[#393939]"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isDiscovering}
                  className="px-4 py-2 bg-[#0f62fe] text-white rounded-sm hover:bg-[#0353e9] disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {isDiscovering ? 'Scanning...' : 'Start Scan'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Devices Table */}
      <div className="bg-white dark:bg-[#262626] rounded-sm shadow-sm border border-[#e0e0e0] dark:border-[#393939] overflow-hidden overflow-x-auto">
        <table className="min-w-full divide-y divide-[#e0e0e0] dark:divide-[#393939]">
          <thead className="bg-[#f4f4f4] dark:bg-[#161616]">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-[#525252] dark:text-[#a8a8a8] uppercase tracking-wider">
                Name
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-[#525252] dark:text-[#a8a8a8] uppercase tracking-wider">
                IP Address
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-[#525252] dark:text-[#a8a8a8] uppercase tracking-wider">
                Community
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-[#525252] dark:text-[#a8a8a8] uppercase tracking-wider">
                Status
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-[#525252] dark:text-[#a8a8a8] uppercase tracking-wider">
                Method
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-[#525252] dark:text-[#a8a8a8] uppercase tracking-wider">
                Last Polled
              </th>
              <th className="px-6 py-3 text-right text-xs font-medium text-[#525252] dark:text-[#a8a8a8] uppercase tracking-wider">
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="bg-white dark:bg-[#262626] divide-y divide-[#e0e0e0] dark:divide-[#393939]">
            {isLoading ? (
              <tr>
                <td colSpan={7} className="px-6 py-8 text-center text-[#525252] dark:text-[#a8a8a8]">
                  Loading devices...
                </td>
              </tr>
            ) : filteredDevices.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-6 py-8 text-center text-[#525252] dark:text-[#a8a8a8]">
                  {devices.length === 0
                    ? 'No devices configured. Add your first device or scan the network.'
                    : 'No devices match your search.'}
                </td>
              </tr>
            ) : (
              filteredDevices.map((device) => (
                <tr key={device.id} className="hover:bg-[#f4f4f4] dark:hover:bg-[#393939]">
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="text-sm font-medium text-[#161616] dark:text-white">
                      {device.name || '-'}
                    </div>
                    {device.sys_descr && (
                      <div className="text-xs text-[#525252] dark:text-[#a8a8a8] truncate max-w-xs" title={device.sys_descr}>
                        {device.sys_descr}
                      </div>
                    )}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="text-sm text-[#161616] dark:text-white font-mono">{device.ip_address}</div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="text-sm text-[#161616] dark:text-white">{device.community}</div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span
                      className={`inline-flex px-2 py-1 rounded-sm text-xs font-medium ${statusBadge(device.status)}`}
                    >
                      {device.status}
                    </span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span className="inline-flex px-2 py-1 rounded-sm text-xs font-medium bg-[#e0e0e0] text-[#161616] dark:bg-[#262626] dark:text-[#a8a8a8]">
                      {device.discovery_method || 'manual'}
                    </span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-[#525252] dark:text-[#a8a8a8]">
                    {device.last_polled || 'Never'}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                    <button
                      onClick={() => handleDelete(device.id)}
                      className="text-[#da1e28] hover:text-red-900 dark:hover:text-red-400 ml-4"
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

export default Devices;
