import { useState, useRef } from 'react';
import { Plus, Search, Trash2, ScanLine, X, Upload, RefreshCcw } from 'lucide-react';
import { useDevices, useDeviceEvents } from '../hooks';
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
  const {
    devices, isLoading, createDevice, deleteDevice,
    discoverNetwork, rescanNetwork, isRescanning,
    isDiscovering,
  } = useDevices();
  useDeviceEvents();
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
  const [scanConfig, setScanConfig] = useState({ network_range: '192.168.1.0/24', community: 'public', method: 'all', replace: true });
  const [busy, setBusy] = useState(false);

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
    setBusy(true);
    try {
      if (scanConfig.replace) {
        const r = await rescanNetwork(scanConfig);
        toast.success(
          'Rescan complete',
          `Cleared ${r.data.cleared ?? 0}, found ${r.data.found}, added ${r.data.added}`,
        );
      } else {
        const r = await discoverNetwork(scanConfig);
        toast.success('Scan complete', `Found ${r.data.found}, added ${r.data.added}`);
      }
      setShowScanModal(false);
    } catch (e: any) {
      toast.error('Scan failed', e?.response?.data?.detail || e?.message);
    } finally { setBusy(false); }
  };

  const handleResetRescan = async () => {
    if (!confirm('Wipe ALL devices & topology, then scan the current range?')) return;
    setBusy(true);
    try {
      const r = await rescanNetwork(scanConfig);
      toast.success(
        'Reset & rescan complete',
        `Cleared ${r.data.cleared ?? 0}, found ${r.data.found}, added ${r.data.added}`,
      );
    } catch (e: any) { toast.error('Failed', e?.response?.data?.detail || e?.message); }
    finally { setBusy(false); }
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

      const r = await apiClient.post('/api/devices/import', { devices });
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
    const m: Record<string, string> = {
      online: 'bg-badge-success-bg text-badge-success-fg',
      offline: 'bg-badge-destructive-bg text-badge-destructive-fg',
      discovered: 'bg-badge-info-bg text-badge-info-fg'
    };
    return m[status] || 'bg-badge-neutral-bg text-badge-neutral-fg';
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-6 gap-4">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Devices</h1>
          <p className="text-muted-foreground mt-1">Manage network devices</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button onClick={handleResetRescan} disabled={busy || isRescanning} className="flex items-center space-x-2 px-4 py-2 bg-btn-destructive text-btn-destructive-foreground rounded-sm hover:bg-btn-destructive-hover disabled:opacity-50">
            <RefreshCcw className="h-4 w-4" /><span>{busy || isRescanning ? 'Rescanning...' : 'Reset & Rescan'}</span>
          </button>
          <button onClick={() => setShowImport(true)} className="flex items-center space-x-2 px-4 py-2 bg-btn-success text-btn-success-foreground rounded-sm hover:bg-btn-success-hover">
            <Upload className="h-4 w-4" /><span>Import</span>
          </button>
          <button onClick={() => setShowScanModal(true)} className="flex items-center space-x-2 px-4 py-2 bg-btn-accent text-btn-accent-foreground rounded-sm hover:bg-btn-accent-hover">
            <ScanLine className="h-4 w-4" /><span>Scan</span>
          </button>
          <button onClick={() => setShowAddForm(true)} className="flex items-center space-x-2 px-4 py-2 bg-btn-primary text-btn-primary-foreground rounded-sm hover:bg-btn-primary-hover">
            <Plus className="h-4 w-4" /><span>Add Device</span>
          </button>
        </div>
      </div>

      <div className="mb-6"><div className="relative"><Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-5 w-5 text-muted-foreground" />
        <input type="text" placeholder="Search..." value={searchTerm} onChange={e => setSearchTerm(e.target.value)}
          className="w-full pl-10 pr-4 py-2 border border-input dark:border-input bg-card text-foreground rounded-sm focus:ring-1 focus:ring-ring" />
      </div></div>

      {showAddForm && (
        <div className="mb-6 bg-card rounded-sm shadow-sm border border-border p-6">
          <h2 className="text-lg font-semibold text-foreground mb-4">Add Device</h2>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div><label className="block text-sm font-medium text-foreground mb-1">Name</label>
                <input type="text" value={newDevice.name} onChange={e => setNewDevice({...newDevice, name: e.target.value})}
                  className="w-full px-3 py-2 border border-input dark:border-input bg-card text-foreground rounded-sm" placeholder="Router-1" /></div>
              <div><label className="block text-sm font-medium text-foreground mb-1">IP Address *</label>
                <input type="text" value={newDevice.ip_address} onChange={e => setNewDevice({...newDevice, ip_address: e.target.value})} required
                  className="w-full px-3 py-2 border border-input dark:border-input bg-card text-foreground rounded-sm" placeholder="192.168.1.1" /></div>
              <div><label className="block text-sm font-medium text-foreground mb-1">SNMP Version</label>
                <select value={newDevice.snmp_version} onChange={e => setNewDevice({...newDevice, snmp_version: e.target.value})}
                  className="w-full px-3 py-2 border border-input dark:border-input bg-card text-foreground rounded-sm">
                  <option value="2c">v2c</option><option value="3">v3</option></select></div>
            </div>
            {newDevice.snmp_version === '2c' && (
              <div><label className="block text-sm font-medium text-foreground mb-1">Community</label>
                <select value={newDevice.community} onChange={e => setNewDevice({...newDevice, community: e.target.value})}
                  className="w-full px-3 py-2 border border-input dark:border-input bg-card text-foreground rounded-sm">
                  <option value="public">public</option><option value="private">private</option></select></div>
            )}
            {newDevice.snmp_version === '3' && (
              <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                <div><label className="block text-sm font-medium text-foreground mb-1">Username</label>
                  <input type="text" value={newDevice.snmpv3_username} onChange={e => setNewDevice({...newDevice, snmpv3_username: e.target.value})}
                    className="w-full px-3 py-2 border border-input dark:border-input bg-card text-foreground rounded-sm" /></div>
                <div><label className="block text-sm font-medium text-foreground mb-1">Auth Protocol</label>
                  <select value={newDevice.snmpv3_auth_protocol} onChange={e => setNewDevice({...newDevice, snmpv3_auth_protocol: e.target.value})}
                    className="w-full px-3 py-2 border border-input dark:border-input bg-card text-foreground rounded-sm">
                    <option value="">none</option><option value="MD5">MD5</option><option value="SHA">SHA</option><option value="SHA256">SHA-256</option></select></div>
                <div><label className="block text-sm font-medium text-foreground mb-1">Auth Key</label>
                  <input type="password" value={newDevice.snmpv3_auth_key} onChange={e => setNewDevice({...newDevice, snmpv3_auth_key: e.target.value})}
                    className="w-full px-3 py-2 border border-input dark:border-input bg-card text-foreground rounded-sm" /></div>
                <div><label className="block text-sm font-medium text-foreground mb-1">Priv Protocol</label>
                  <select value={newDevice.snmpv3_priv_protocol} onChange={e => setNewDevice({...newDevice, snmpv3_priv_protocol: e.target.value})}
                    className="w-full px-3 py-2 border border-input dark:border-input bg-card text-foreground rounded-sm">
                    <option value="">none</option><option value="DES">DES</option><option value="AES">AES</option></select></div>
                <div><label className="block text-sm font-medium text-foreground mb-1">Priv Key</label>
                  <input type="password" value={newDevice.snmpv3_priv_key} onChange={e => setNewDevice({...newDevice, snmpv3_priv_key: e.target.value})}
                    className="w-full px-3 py-2 border border-input dark:border-input bg-card text-foreground rounded-sm" /></div>
              </div>
            )}
            <div className="flex justify-end space-x-2">
              <button type="button" onClick={() => setShowAddForm(false)} className="px-4 py-2 text-foreground bg-secondary hover:bg-surface-hover rounded-sm">Cancel</button>
              <button type="submit" className="px-4 py-2 bg-btn-primary text-btn-primary-foreground rounded-sm hover:bg-btn-primary-hover">Add Device</button>
            </div>
          </form>
        </div>
      )}

      {showImport && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-card rounded-sm shadow-lg border border-border p-6 w-full max-w-lg mx-4">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-lg font-semibold text-foreground">Bulk Import Devices</h2>
              <button onClick={() => { setShowImport(false); setImportData(''); }} className="text-muted-foreground hover:text-foreground"><X className="h-5 w-5" /></button>
            </div>
            <div className="space-y-4">
              <div className="flex space-x-2">
                <button onClick={() => setImportType('json')} className={`px-3 py-1.5 text-sm rounded-sm ${importType === 'json' ? 'bg-btn-primary text-btn-primary-foreground' : 'bg-secondary text-secondary-foreground'}`}>JSON</button>
                <button onClick={() => setImportType('csv')} className={`px-3 py-1.5 text-sm rounded-sm ${importType === 'csv' ? 'bg-btn-primary text-btn-primary-foreground' : 'bg-secondary text-secondary-foreground'}`}>CSV</button>
                <button onClick={() => fileRef.current?.click()} className="px-3 py-1.5 text-sm rounded-sm bg-btn-accent text-btn-accent-foreground hover:bg-btn-accent-hover">Upload File</button>
                <input ref={fileRef} type="file" accept=".json,.csv" onChange={handleFileUpload} className="hidden" />
              </div>
              <textarea value={importData} onChange={e => setImportData(e.target.value)}
                className="w-full h-48 px-3 py-2 border border-input dark:border-input bg-card text-foreground rounded-sm font-mono text-xs"
                placeholder={importType === 'json' ? '[{"name":"Router-1","ip_address":"192.168.1.1","community":"public"}]' : 'name,ip_address,community,SNMP_version\nRouter-1,192.168.1.1,public,2c'} />
              <div className="flex justify-end space-x-2">
                <button onClick={() => { setShowImport(false); setImportData(''); }} className="px-4 py-2 text-foreground bg-secondary hover:bg-surface-hover rounded-sm">Cancel</button>
                <button onClick={handleImport} disabled={importing} className="px-4 py-2 bg-btn-success text-btn-success-foreground rounded-sm hover:bg-btn-success-hover disabled:opacity-50">{importing ? 'Importing...' : 'Import'}</button>
              </div>
            </div>
          </div>
        </div>
      )}

      {showScanModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-card rounded-sm shadow-lg border border-border p-6 w-full max-w-md mx-4">
            <div className="flex justify-between items-center mb-4"><h2 className="text-lg font-semibold text-foreground">Scan Network</h2><button onClick={() => setShowScanModal(false)} className="text-muted-foreground"><X className="h-5 w-5" /></button></div>
            <form onSubmit={handleDiscover} className="space-y-4">
              <div><label className="block text-sm font-medium text-foreground mb-1">Network Range</label>
                <input type="text" value={scanConfig.network_range} onChange={e => setScanConfig({...scanConfig, network_range: e.target.value})} required
                  className="w-full px-3 py-2 border border-input dark:border-input bg-card text-foreground rounded-sm" placeholder="192.168.1.0/24" /></div>
              <div><label className="block text-sm font-medium text-foreground mb-1">SNMP Community</label>
                <select value={scanConfig.community} onChange={e => setScanConfig({...scanConfig, community: e.target.value})}
                  className="w-full px-3 py-2 border border-input dark:border-input bg-card text-foreground rounded-sm"><option value="public">public</option><option value="private">private</option></select></div>
              <label className="flex items-center space-x-2 text-sm text-foreground">
                <input type="checkbox" checked={scanConfig.replace} onChange={e => setScanConfig({...scanConfig, replace: e.target.checked})}
                  className="h-4 w-4 rounded border-input text-destructive focus:ring-ring" />
                <span>Replace existing devices (clear DB before scan)</span>
              </label>
              <div className="flex justify-end space-x-2">
                <button type="button" onClick={() => setShowScanModal(false)} className="px-4 py-2 text-foreground bg-secondary hover:bg-surface-hover rounded-sm">Cancel</button>
                <button type="submit" disabled={busy || isDiscovering || isRescanning} className="px-4 py-2 bg-btn-accent text-btn-accent-foreground rounded-sm hover:bg-btn-accent-hover disabled:opacity-50">
                  {busy || isRescanning ? 'Working...' : (scanConfig.replace ? 'Reset & Scan' : 'Start Scan')}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      <div className="bg-card rounded-sm shadow-sm border border-border overflow-hidden overflow-x-auto">
        <table className="min-w-full divide-y divide-border">
          <thead className="bg-background">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase">Name</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase">IP</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase">Ver</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase">Status</th>
              <th className="px-6 py-3 text-right text-xs font-medium text-muted-foreground uppercase">Actions</th>
            </tr>
          </thead>
          <tbody className="bg-card divide-y divide-border">
            {isLoading ? (
              <tr><td colSpan={5} className="px-6 py-8 text-center text-muted-foreground">Loading...</td></tr>
            ) : filteredDevices.length === 0 ? (
              <tr><td colSpan={5} className="px-6 py-8 text-center text-muted-foreground">No devices found</td></tr>
            ) : filteredDevices.map(device => (
              <tr key={device.id} className="hover:bg-muted dark:hover:bg-muted">
                <td className="px-6 py-4"><div className="text-sm font-medium text-foreground">{device.name || '-'}</div>
                  {device.sys_descr && <div className="text-xs text-muted-foreground truncate max-w-xs" title={device.sys_descr}>{device.sys_descr}</div>}</td>
                <td className="px-6 py-4"><div className="text-sm font-mono text-foreground">{device.ip_address}</div></td>
                <td className="px-6 py-4"><span className="inline-flex px-2 py-0.5 text-xs rounded-sm bg-badge-neutral-bg text-badge-neutral-fg">{device.snmp_version || '2c'}</span></td>
                <td className="px-6 py-4"><span className={`inline-flex px-2 py-1 rounded-sm text-xs font-medium ${statusBadge(device.status)}`}>{device.status}</span></td>
                <td className="px-6 py-4 text-right"><button onClick={() => handleDelete(device.id)} className="text-destructive hover:text-red-900 dark:hover:text-red-400"><Trash2 className="h-4 w-4" /></button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default Devices;