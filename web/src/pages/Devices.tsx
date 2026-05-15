import { useState, useRef } from 'react';
import { Plus, Search, Trash2, ScanLine, X, Upload, Globe } from 'lucide-react';
import { useDevices } from '../hooks/useDevices';
import { useToast } from '../components/ui';
import apiClient from '../api/client';

function parseCSV(text: string): Record<string, string>[] {
  const lines = text.trim().split('\n');
  if (lines.length < 2) return [];
  const headers = lines[0].split(',').map(h => h.trim().toLowerCase());
  return lines.slice(1).filter(l => l.trim()).map(line => {
    const vals = line.split(',').map(v => v.trim());
    const obj: Record<string, string> = {};
    headers.forEach((h, i) => { obj[h] = vals[i] || ''; });
    return obj;
  });
}

export function Devices() {
  const { devices, isLoading, createDevice, deleteDevice, discoverNetwork, isDiscovering } = useDevices();
  const toast = useToast();
  const [showAddForm, setShowAddForm] = useState(false);
  const [showScanModal, setShowScanModal] = useState(false);
  const [showImport, setShowImport] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [importData, setImportData] = useState('');
  const [importType, setImportType] = useState<'json' | 'csv'>('json');
  const [importing, setImporting] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const [newDevice, setNewDevice] = useState<any>({
    name: '', ip_address: '', community: 'public',
    snmp_version: '2c', snmpv3_username: '', snmpv3_auth_protocol: '',
    snmpv3_auth_key: '', snmpv3_priv_protocol: '', snmpv3_priv_key: '',
  });
  const [scanConfig, setScanConfig] = useState({ network_range: '192.168.1.0/24', community: 'public', method: 'all' });

  const filteredDevices = devices.filter(
    (d) => d.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
           d.ip_address.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await createDevice(newDevice);
      toast.success('Device added', `${newDevice.name || newDevice.ip_address}`);
      setShowAddForm(false);
    } catch { toast.error('Failed to add device'); }
  };

  const handleDelete = async (id: string) => {
    if (confirm('Delete this device?')) { try { await deleteDevice(id); toast.success('Deleted'); } catch { toast.error('Failed'); } }
  };

  const handleDiscover = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const r = await discoverNetwork(scanConfig);
      toast.success('Scan complete', `Found ${r.data.found}, added ${r.data.added}`);
      setShowScanModal(false);
    } catch { toast.error('Scan failed'); }
  };

  const handleImport = async () => {
    if (!importData.trim()) return;
    setImporting(true);
    try {
      let devices: any[] = [];
      if (importType === 'json') {
        const parsed = JSON.parse(importData);
        devices = Array.isArray(parsed) ? parsed : parsed.devices || [];
      } else {
        const rows = parseCSV(importData);
        devices = rows.map(r => ({
          name: r.name || r.hostname || '',
          ip_address: r.ip_address || r.ip || r.address || '',
          community: r.community || 'public',
          snmp_version: r.snmp_version || '2c',
        })).filter(d => d.ip_address);
      }

      const r = await apiClient.post('/devices/import', { devices });
      toast.success(`Imported ${r.data.created} devices`, `${r.data.skipped} skipped, ${r.data.errors.length} errors`);
      setShowImport(false); setImportData('');
    } catch (e: any) {
      toast.error('Import failed', e?.response?.data?.detail || e.message);
    } finally { setImporting(false); }
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const ext = file.name.split('.').pop()?.toLowerCase();
    setImportType(ext === 'csv' ? 'csv' : 'json');
    const reader = new FileReader();
    reader.onload = () => setImportData(reader.result as string);
    reader.readAsText(file);
  };

  const statusBadge = (status: string) => {
    const m: Record<string, string> = { online: 'bg-[#defbe6] text-[#24a148]', offline: 'bg-[#fff0f1] text-[#da1e28]', discovered: 'bg-[#e0e0e0] text-[#0f62fe]' };
    return m[status] || 'bg-[#e0e0e0] text-[#161616]';
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-6 gap-4">
        <div>
          <h1 className="text-2xl font-bold text-[#161616] dark:text-white">Devices</h1>
          <p className="text-[#525252] dark:text-[#a8a8a8] mt-1">Manage network devices</p>
        </div>
        <div className="flex space-x-2">
          <button onClick={() => setShowImport(true)} className="flex items-center space-x-2 px-4 py-2 bg-[#24a148] text-white rounded-sm hover:bg-[#1a7a34]">
            <Upload className="h-4 w-4" /><span>Import</span>
          </button>
          <button onClick={() => setShowScanModal(true)} className="flex items-center space-x-2 px-4 py-2 bg-[#0f62fe] text-white rounded-sm hover:bg-[#0353e9]">
            <ScanLine className="h-4 w-4" /><span>Scan</span>
          </button>
          <button onClick={() => setShowAddForm(true)} className="flex items-center space-x-2 px-4 py-2 bg-[#161616] text-white rounded-sm hover:bg-[#525252]">
            <Plus className="h-4 w-4" /><span>Add Device</span>
          </button>
        </div>
      </div>

      <div className="mb-6"><div className="relative"><Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-5 w-5 text-[#a8a8a8]" />
        <input type="text" placeholder="Search..." value={searchTerm} onChange={e => setSearchTerm(e.target.value)}
          className="w-full pl-10 pr-4 py-2 border border-[#c6c6c6] dark:border-[#525252] bg-white dark:bg-[#262626] text-[#161616] dark:text-white rounded-sm focus:ring-1 focus:ring-[#da1e28]" />
      </div></div>

      {showAddForm && (
        <div className="mb-6 bg-white dark:bg-[#262626] rounded-sm shadow-sm border border-[#e0e0e0] dark:border-[#393939] p-6">
          <h2 className="text-lg font-semibold text-[#161616] dark:text-white mb-4">Add Device</h2>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div><label className="block text-sm font-medium text-[#161616] dark:text-[#a8a8a8] mb-1">Name</label>
                <input type="text" value={newDevice.name} onChange={e => setNewDevice({...newDevice, name: e.target.value})}
                  className="w-full px-3 py-2 border border-[#c6c6c6] dark:border-[#525252] bg-white dark:bg-[#262626] text-[#161616] dark:text-white rounded-sm" placeholder="Router-1" /></div>
              <div><label className="block text-sm font-medium text-[#161616] dark:text-[#a8a8a8] mb-1">IP Address *</label>
                <input type="text" value={newDevice.ip_address} onChange={e => setNewDevice({...newDevice, ip_address: e.target.value})} required
                  className="w-full px-3 py-2 border border-[#c6c6c6] dark:border-[#525252] bg-white dark:bg-[#262626] text-[#161616] dark:text-white rounded-sm" placeholder="192.168.1.1" /></div>
              <div><label className="block text-sm font-medium text-[#161616] dark:text-[#a8a8a8] mb-1">SNMP Version</label>
                <select value={newDevice.snmp_version} onChange={e => setNewDevice({...newDevice, snmp_version: e.target.value})}
                  className="w-full px-3 py-2 border border-[#c6c6c6] dark:border-[#525252] bg-white dark:bg-[#262626] text-[#161616] dark:text-white rounded-sm">
                  <option value="2c">v2c</option><option value="3">v3</option></select></div>
            </div>
            {newDevice.snmp_version === '2c' && (
              <div><label className="block text-sm font-medium text-[#161616] dark:text-[#a8a8a8] mb-1">Community</label>
                <select value={newDevice.community} onChange={e => setNewDevice({...newDevice, community: e.target.value})}
                  className="w-full px-3 py-2 border border-[#c6c6c6] dark:border-[#525252] bg-white dark:bg-[#262626] text-[#161616] dark:text-white rounded-sm">
                  <option value="public">public</option><option value="private">private</option></select></div>
            )}
            {newDevice.snmp_version === '3' && (
              <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                <div><label className="block text-sm font-medium text-[#161616] dark:text-[#a8a8a8] mb-1">Username</label>
                  <input type="text" value={newDevice.snmpv3_username} onChange={e => setNewDevice({...newDevice, snmpv3_username: e.target.value})}
                    className="w-full px-3 py-2 border border-[#c6c6c6] dark:border-[#525252] bg-white dark:bg-[#262626] text-[#161616] dark:text-white rounded-sm" /></div>
                <div><label className="block text-sm font-medium text-[#161616] dark:text-[#a8a8a8] mb-1">Auth Protocol</label>
                  <select value={newDevice.snmpv3_auth_protocol} onChange={e => setNewDevice({...newDevice, snmpv3_auth_protocol: e.target.value})}
                    className="w-full px-3 py-2 border border-[#c6c6c6] dark:border-[#525252] bg-white dark:bg-[#262626] text-[#161616] dark:text-white rounded-sm">
                    <option value="">none</option><option value="MD5">MD5</option><option value="SHA">SHA</option><option value="SHA256">SHA-256</option></select></div>
                <div><label className="block text-sm font-medium text-[#161616] dark:text-[#a8a8a8] mb-1">Auth Key</label>
                  <input type="password" value={newDevice.snmpv3_auth_key} onChange={e => setNewDevice({...newDevice, snmpv3_auth_key: e.target.value})}
                    className="w-full px-3 py-2 border border-[#c6c6c6] dark:border-[#525252] bg-white dark:bg-[#262626] text-[#161616] dark:text-white rounded-sm" /></div>
                <div><label className="block text-sm font-medium text-[#161616] dark:text-[#a8a8a8] mb-1">Priv Protocol</label>
                  <select value={newDevice.snmpv3_priv_protocol} onChange={e => setNewDevice({...newDevice, snmpv3_priv_protocol: e.target.value})}
                    className="w-full px-3 py-2 border border-[#c6c6c6] dark:border-[#525252] bg-white dark:bg-[#262626] text-[#161616] dark:text-white rounded-sm">
                    <option value="">none</option><option value="DES">DES</option><option value="AES">AES</option></select></div>
                <div><label className="block text-sm font-medium text-[#161616] dark:text-[#a8a8a8] mb-1">Priv Key</label>
                  <input type="password" value={newDevice.snmpv3_priv_key} onChange={e => setNewDevice({...newDevice, snmpv3_priv_key: e.target.value})}
                    className="w-full px-3 py-2 border border-[#c6c6c6] dark:border-[#525252] bg-white dark:bg-[#262626] text-[#161616] dark:text-white rounded-sm" /></div>
              </div>
            )}
            <div className="flex justify-end space-x-2">
              <button type="button" onClick={() => setShowAddForm(false)} className="px-4 py-2 text-[#161616] dark:text-[#a8a8a8] bg-[#e0e0e0] dark:bg-[#262626] rounded-sm hover:bg-[#e0e0e0] dark:hover:bg-[#393939]">Cancel</button>
              <button type="submit" className="px-4 py-2 bg-[#161616] text-white rounded-sm hover:bg-[#525252]">Add Device</button>
            </div>
          </form>
        </div>
      )}

      {showImport && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-white dark:bg-[#262626] rounded-sm shadow-lg border border-[#e0e0e0] dark:border-[#393939] p-6 w-full max-w-lg mx-4">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-lg font-semibold text-[#161616] dark:text-white">Bulk Import Devices</h2>
              <button onClick={() => { setShowImport(false); setImportData(''); }} className="text-[#a8a8a8] hover:text-[#525252]"><X className="h-5 w-5" /></button>
            </div>
            <div className="space-y-4">
              <div className="flex space-x-2">
                <button onClick={() => setImportType('json')} className={`px-3 py-1.5 text-sm rounded-sm ${importType === 'json' ? 'bg-[#161616] text-white' : 'bg-[#e0e0e0] dark:bg-[#393939] text-[#161616] dark:text-[#a8a8a8]'}`}>JSON</button>
                <button onClick={() => setImportType('csv')} className={`px-3 py-1.5 text-sm rounded-sm ${importType === 'csv' ? 'bg-[#161616] text-white' : 'bg-[#e0e0e0] dark:bg-[#393939] text-[#161616] dark:text-[#a8a8a8]'}`}>CSV</button>
                <button onClick={() => fileRef.current?.click()} className="px-3 py-1.5 text-sm rounded-sm bg-[#0f62fe] text-white hover:bg-[#0353e9]">Upload File</button>
                <input ref={fileRef} type="file" accept=".json,.csv" onChange={handleFileUpload} className="hidden" />
              </div>
              <textarea value={importData} onChange={e => setImportData(e.target.value)}
                className="w-full h-48 px-3 py-2 border border-[#c6c6c6] dark:border-[#525252] bg-white dark:bg-[#262626] text-[#161616] dark:text-white rounded-sm font-mono text-xs"
                placeholder={importType === 'json' ? '[{"name":"Router-1","ip_address":"192.168.1.1","community":"public"}]' : 'name,ip_address,community,SNMP_version\nRouter-1,192.168.1.1,public,2c'} />
              <div className="flex justify-end space-x-2">
                <button onClick={() => { setShowImport(false); setImportData(''); }} className="px-4 py-2 text-[#161616] bg-[#e0e0e0] rounded-sm">Cancel</button>
                <button onClick={handleImport} disabled={importing} className="px-4 py-2 bg-[#24a148] text-white rounded-sm hover:bg-[#1a7a34] disabled:opacity-50">{importing ? 'Importing...' : 'Import'}</button>
              </div>
            </div>
          </div>
        </div>
      )}

      {showScanModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-white dark:bg-[#262626] rounded-sm shadow-lg border border-[#e0e0e0] dark:border-[#393939] p-6 w-full max-w-md mx-4">
            <div className="flex justify-between items-center mb-4"><h2 className="text-lg font-semibold text-[#161616] dark:text-white">Scan Network</h2><button onClick={() => setShowScanModal(false)} className="text-[#a8a8a8]"><X className="h-5 w-5" /></button></div>
            <form onSubmit={handleDiscover} className="space-y-4">
              <div><label className="block text-sm font-medium text-[#161616] dark:text-[#a8a8a8] mb-1">Network Range</label>
                <input type="text" value={scanConfig.network_range} onChange={e => setScanConfig({...scanConfig, network_range: e.target.value})} required
                  className="w-full px-3 py-2 border border-[#c6c6c6] dark:border-[#525252] bg-white dark:bg-[#262626] text-[#161616] dark:text-white rounded-sm" placeholder="192.168.1.0/24" /></div>
              <div><label className="block text-sm font-medium text-[#161616] dark:text-[#a8a8a8] mb-1">SNMP Community</label>
                <select value={scanConfig.community} onChange={e => setScanConfig({...scanConfig, community: e.target.value})}
                  className="w-full px-3 py-2 border border-[#c6c6c6] dark:border-[#525252] bg-white dark:bg-[#262626] text-[#161616] dark:text-white rounded-sm"><option value="public">public</option><option value="private">private</option></select></div>
              <div className="flex justify-end space-x-2">
                <button type="button" onClick={() => setShowScanModal(false)} className="px-4 py-2 text-[#161616] bg-[#e0e0e0] rounded-sm">Cancel</button>
                <button type="submit" disabled={isDiscovering} className="px-4 py-2 bg-[#0f62fe] text-white rounded-sm disabled:opacity-50">{isDiscovering ? 'Scanning...' : 'Start Scan'}</button>
              </div>
            </form>
          </div>
        </div>
      )}

      <div className="bg-white dark:bg-[#262626] rounded-sm shadow-sm border border-[#e0e0e0] dark:border-[#393939] overflow-hidden overflow-x-auto">
        <table className="min-w-full divide-y divide-[#e0e0e0] dark:divide-[#393939]">
          <thead className="bg-[#f4f4f4] dark:bg-[#161616]">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-[#525252] dark:text-[#a8a8a8] uppercase">Name</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-[#525252] dark:text-[#a8a8a8] uppercase">IP</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-[#525252] dark:text-[#a8a8a8] uppercase">Ver</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-[#525252] dark:text-[#a8a8a8] uppercase">Status</th>
              <th className="px-6 py-3 text-right text-xs font-medium text-[#525252] dark:text-[#a8a8a8] uppercase">Actions</th>
            </tr>
          </thead>
          <tbody className="bg-white dark:bg-[#262626] divide-y divide-[#e0e0e0] dark:divide-[#393939]">
            {isLoading ? (
              <tr><td colSpan={5} className="px-6 py-8 text-center text-[#525252] dark:text-[#a8a8a8]">Loading...</td></tr>
            ) : filteredDevices.length === 0 ? (
              <tr><td colSpan={5} className="px-6 py-8 text-center text-[#525252] dark:text-[#a8a8a8]">No devices found</td></tr>
            ) : filteredDevices.map(device => (
              <tr key={device.id} className="hover:bg-[#f4f4f4] dark:hover:bg-[#393939]">
                <td className="px-6 py-4"><div className="text-sm font-medium text-[#161616] dark:text-white">{device.name || '-'}</div>
                  {device.sys_descr && <div className="text-xs text-[#525252] dark:text-[#a8a8a8] truncate max-w-xs" title={device.sys_descr}>{device.sys_descr}</div>}</td>
                <td className="px-6 py-4"><div className="text-sm font-mono text-[#161616] dark:text-white">{device.ip_address}</div></td>
                <td className="px-6 py-4"><span className="inline-flex px-2 py-0.5 text-xs rounded-sm bg-[#e0e0e0] dark:bg-[#393939] text-[#161616] dark:text-[#a8a8a8]">{device.snmp_version || '2c'}</span></td>
                <td className="px-6 py-4"><span className={`inline-flex px-2 py-1 rounded-sm text-xs font-medium ${statusBadge(device.status)}`}>{device.status}</span></td>
                <td className="px-6 py-4 text-right"><button onClick={() => handleDelete(device.id)} className="text-[#da1e28] hover:text-red-900 dark:hover:text-red-400"><Trash2 className="h-4 w-4" /></button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default Devices;
