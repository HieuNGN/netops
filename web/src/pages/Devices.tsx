import { useState, useRef } from 'react';
import { Link } from 'react-router-dom';
import { Plus, Search, Trash2, ScanLine, X, Upload, RefreshCcw, AlertTriangle, Server, Filter, Pencil, Check, Download } from 'lucide-react';
import { useDevices, useDeviceEvents, useNetworks, useStaleAction } from '../hooks';
import { useToast } from '../components/ui';
import { FilterSelect } from '../components/ui/FilterSelect';
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
    devices, isLoading, createDevice, deleteDevice, updateDevice,
    rescanNetwork, isRescanning,
    scanLog, scanProgress, clearScanLog,
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
  const [scanConfig, setScanConfig] = useState({ network_range: '192.168.1.0/24', community: 'public', method: 'all' });
  const [busy, setBusy] = useState(false);
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [methodFilter, setMethodFilter] = useState<string>('all');
  const [networkFilter, setNetworkFilter] = useState<string>('all');
  const [tagFilter, setTagFilter] = useState<string>('all');
  const [staleModalDevice, setStaleModalDevice] = useState<any | null>(null);
  const [showResetConfirm, setShowResetConfirm] = useState(false);
  const [deleteTargetId, setDeleteTargetId] = useState<string | null>(null);
  const [editingDeviceId, setEditingDeviceId] = useState<string | null>(null);
  const [editName, setEditName] = useState('');
  const { networks } = useNetworks();
  const staleActionMutation = useStaleAction();

  const filteredDevices = devices.filter(
    (d) =>
      (d.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
        d.ip_address.toLowerCase().includes(searchTerm.toLowerCase())) &&
      (statusFilter === 'all' || d.status === statusFilter) &&
      (methodFilter === 'all' || d.discovery_method === methodFilter) &&
      (networkFilter === 'all' || d.network_id === networkFilter) &&
      (tagFilter === 'all' ||
        (Array.isArray((d as any).tags) && (d as any).tags.includes(tagFilter))),
  );

  const allTags = Array.from(
    new Set(
      devices.flatMap((d: any) => (Array.isArray(d.tags) ? d.tags : [])),
    ),
  );

  const isStale = (device: any): boolean => {
    if (device.status !== 'offline' || !device.offline_since) return false;
    const since = new Date(device.offline_since).getTime();
    return Date.now() - since > 72 * 3600 * 1000;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await createDevice(newDevice);
      toast.success('Device added', `${newDevice.name || newDevice.ip_address}`);
      setShowAddForm(false);
    } catch { toast.error('Failed to add device'); }
  };
  const handleDelete = async (id: string) => {
    setDeleteTargetId(id);
  };

  const confirmDelete = async () => {
    if (!deleteTargetId) return;
    try { await deleteDevice(deleteTargetId); toast.success('Deleted'); } catch { toast.error('Failed'); }
    setDeleteTargetId(null);
  };

  const startEditName = (device: any) => {
    setEditingDeviceId(device.id);
    setEditName(device.name || '');
  };

  const saveDeviceName = async (id: string) => {
    if (!editName.trim()) return;
    try {
      await updateDevice({ id, data: { name: editName.trim() } });
      toast.success('Device name updated');
    } catch { toast.error('Failed to update name'); }
    setEditingDeviceId(null);
    setEditName('');
  };

  const cancelEditName = () => {
    setEditingDeviceId(null);
    setEditName('');
  };

  const handleDiscover = async (e: React.FormEvent) => {
    e.preventDefault();
    clearScanLog();
    setBusy(true);
    try {
      // Default = merge (non-destructive). Replace path is only for the
      // explicit "Reset & Rescan" button.

      const r = await rescanNetwork({ ...scanConfig, mode: 'merge' });
      toast.success(
        'Rescan complete',
        `Found ${r.data.found}, added ${r.data.added}, updated ${r.data.updated ?? 0}`,
      );
      setShowScanModal(false);
    } catch (e: any) {
      toast.error('Scan failed', e?.response?.data?.detail || e?.message);
    } finally { setBusy(false); }
  };

  const confirmResetRescan = async () => {
    setShowResetConfirm(false);
    clearScanLog();
    setBusy(true);
    try {
      const r = await rescanNetwork({ ...scanConfig, mode: 'replace' });
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
      discovered: 'bg-badge-info-bg text-badge-info-fg',
      unknown: 'bg-badge-neutral-bg text-badge-neutral-fg',
    };
    return m[status] || 'bg-badge-neutral-bg text-badge-neutral-fg';
  };

  const statusDot: Record<string, string> = {
    online: 'bg-cisco-green',
    offline: 'bg-thinkpad-red',
    discovered: 'bg-cisco-blue',
    unknown: 'bg-muted-foreground',
  };

  const filterCount = filteredDevices.length;
  const hasFilters =
    searchTerm !== '' ||
    statusFilter !== 'all' ||
    methodFilter !== 'all' ||
    networkFilter !== 'all' ||
    tagFilter !== 'all';

  const exportCSV = () => {
    const headers = ['name', 'ip_address', 'status', 'network', 'method', 'last_polled'];
    const rows = filteredDevices.map(d => {
      const network = networks.find(n => n.id === d.network_id);
      return [
        d.name || '',
        d.ip_address,
        d.status,
        network?.name || '',
        d.discovery_method || '',
        d.last_polled ? new Date(d.last_polled).toISOString() : '',
      ].map(v => `"${String(v).replace(/"/g, '""')}"`).join(',');
    });
    const csv = [headers.join(','), ...rows].join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `devices-${new Date().toISOString().split('T')[0]}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-6 gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-foreground">Devices</h1>
          <p className="text-sm text-muted-foreground mt-1">
            {devices.length} total
            {hasFilters && (
              <>
                {' '}&middot;{' '}
                <span className="text-foreground font-medium tabular-nums">{filterCount}</span> matching
              </>
            )}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => setShowResetConfirm(true)}
            disabled={busy || isRescanning}
            className="inline-flex items-center gap-1.5 text-sm px-3 py-1.5 bg-thinkpad-red text-white rounded-sm hover:bg-thinkpad-red-hover disabled:opacity-50"
          >
            <RefreshCcw className="h-3.5 w-3.5" />
            <span>{busy || isRescanning ? 'Rescanning...' : 'Reset & Rescan'}</span>
          </button>
          <button
            onClick={() => setShowImport(true)}
            className="inline-flex items-center gap-1.5 text-sm px-3 py-1.5 bg-ibm-green text-white rounded-sm hover:bg-ibm-green-hover"
          >
            <Upload className="h-3.5 w-3.5" />
            <span>Import</span>
          </button>
          <button
            onClick={exportCSV}
            disabled={filteredDevices.length === 0}
            className="inline-flex items-center gap-1.5 text-sm px-3 py-1.5 bg-ibm-cyan text-white rounded-sm hover:bg-ibm-cyan-hover disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Download className="h-3.5 w-3.5" />
            <span>Export CSV</span>
          </button>
          <button
            onClick={() => setShowScanModal(true)}
            className="inline-flex items-center gap-1.5 text-sm px-3 py-1.5 bg-cisco-blue text-white rounded-sm hover:bg-cisco-blue-hover"
          >
            <ScanLine className="h-3.5 w-3.5" />
            <span>Scan</span>
          </button>
          <button
            onClick={() => setShowAddForm(true)}
            className="inline-flex items-center gap-1.5 text-sm px-3 py-1.5 bg-ibm-purple text-white rounded-sm hover:bg-ibm-purple-hover"
          >
            <Plus className="h-3.5 w-3.5" />
            <span>Add Device</span>
          </button>
        </div>
      </div>

      <div className="mb-4 flex flex-col sm:flex-row gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
          <input
            type="text"
            placeholder="Search by name or IP…"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full pl-9 pr-3 py-1.5 text-sm border border-input bg-card text-foreground rounded-sm focus:outline-none focus:ring-1 focus:ring-ibm-blue focus:border-ibm-blue"
          />
        </div>
        <div className="flex flex-wrap gap-1.5">
          <FilterSelect label="status" value={statusFilter} onChange={setStatusFilter} options={[
            { value: 'online', label: 'online' },
            { value: 'offline', label: 'offline' },
            { value: 'unknown', label: 'unknown' },
            { value: 'discovered', label: 'discovered' },
          ]} />
          <FilterSelect label="method" value={methodFilter} onChange={setMethodFilter} options={[
            { value: 'manual', label: 'manual' },
            { value: 'snmp', label: 'snmp' },
            { value: 'ping', label: 'ping' },
            { value: 'llsp', label: 'llsp' },
          ]} />
          <FilterSelect
            label="network"
            value={networkFilter}
            onChange={setNetworkFilter}
            options={networks.map((n) => ({ value: n.id, label: n.name }))}
          />
          {allTags.length > 0 && (
            <FilterSelect label="tag" value={tagFilter} onChange={setTagFilter} options={allTags.map((t) => ({ value: t, label: t }))} />
          )}
          {hasFilters && (
            <button
              onClick={() => {
                setSearchTerm('');
                setStatusFilter('all');
                setMethodFilter('all');
                setNetworkFilter('all');
                setTagFilter('all');
              }}
              className="text-xs px-2 py-1 text-muted-foreground hover:text-foreground"
            >
              clear
            </button>
          )}
        </div>
      </div>

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
              <button type="submit" className="px-4 py-2 bg-ibm-purple text-white rounded-sm hover:bg-ibm-purple-hover">Add Device</button>
            </div>
          </form>
        </div>
      )}

      {showImport && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/20">
          <div className="bg-card rounded-sm shadow-lg border border-border p-6 w-full max-w-lg mx-4">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-lg font-semibold text-foreground">Bulk Import Devices</h2>
              <button onClick={() => { setShowImport(false); setImportData(''); }} className="text-muted-foreground hover:text-foreground"><X className="h-5 w-5" /></button>
            </div>
            <div className="space-y-4">
              <div className="flex space-x-2">
                <button onClick={() => setImportType('json')} className={`px-3 py-1.5 text-sm rounded-sm ${importType === 'json' ? 'bg-ibm-blue text-white' : 'bg-secondary text-secondary-foreground'}`}>JSON</button>
                <button onClick={() => setImportType('csv')} className={`px-3 py-1.5 text-sm rounded-sm ${importType === 'csv' ? 'bg-ibm-blue text-white' : 'bg-secondary text-secondary-foreground'}`}>CSV</button>
                <button onClick={() => fileRef.current?.click()} className="px-3 py-1.5 text-sm rounded-sm bg-ibm-cyan text-white hover:bg-ibm-cyan-hover">Upload File</button>
                <input ref={fileRef} type="file" accept=".json,.csv" onChange={handleFileUpload} className="hidden" />
              </div>
              <textarea value={importData} onChange={e => setImportData(e.target.value)}
                className="w-full h-48 px-3 py-2 border border-input dark:border-input bg-card text-foreground rounded-sm font-mono text-xs"
                placeholder={importType === 'json' ? '[{"name":"Router-1","ip_address":"192.168.1.1","community":"public"}]' : 'name,ip_address,community,SNMP_version\nRouter-1,192.168.1.1,public,2c'} />
              <div className="flex justify-end space-x-2">
                <button onClick={() => { setShowImport(false); setImportData(''); }} className="px-4 py-2 text-foreground bg-secondary hover:bg-surface-hover rounded-sm">Cancel</button>
                <button onClick={handleImport} disabled={importing} className="px-4 py-2 bg-ibm-green text-white rounded-sm hover:bg-ibm-green-hover disabled:opacity-50">{importing ? 'Importing...' : 'Import'}</button>
              </div>
            </div>
          </div>
        </div>
      )}

      {showScanModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/20">
          <div className="bg-card rounded-sm shadow-lg border border-border p-6 w-full max-w-lg mx-4 flex flex-col max-h-[80vh]">
            <div className="flex justify-between items-center mb-4"><h2 className="text-lg font-semibold text-foreground">Scan Network</h2><button onClick={() => { setShowScanModal(false); clearScanLog(); }} className="text-muted-foreground"><X className="h-5 w-5" /></button></div>
            <form onSubmit={handleDiscover} className="space-y-4 shrink-0">
              <div><label className="block text-sm font-medium text-foreground mb-1">Network Range</label>
                <input type="text" value={scanConfig.network_range} onChange={e => setScanConfig({...scanConfig, network_range: e.target.value})} required
                  className="w-full px-3 py-2 border border-input dark:border-input bg-card text-foreground rounded-sm" placeholder="192.168.1.0/24" /></div>
              <div><label className="block text-sm font-medium text-foreground mb-1">SNMP Community</label>
                <select value={scanConfig.community} onChange={e => setScanConfig({...scanConfig, community: e.target.value})}
                  className="w-full px-3 py-2 border border-input dark:border-input bg-card text-foreground rounded-sm"><option value="public">public</option><option value="private">private</option></select></div>
              <label className="flex items-center space-x-2 text-sm text-foreground">
                <input
                  type="checkbox"
                  id="scan-merge"
                  defaultChecked
                  className="h-4 w-4 rounded border-input text-destructive focus:ring-ring"
                />
                <span>Preserve manual devices (merge mode)</span>
              </label>
              <div className="flex justify-end space-x-2">
                <button type="button" onClick={() => { setShowScanModal(false); clearScanLog(); }} className="px-4 py-2 text-foreground bg-secondary hover:bg-surface-hover rounded-sm">Cancel</button>
                <button type="submit" disabled={busy || isRescanning} className="px-4 py-2 bg-cisco-blue text-white rounded-sm hover:bg-cisco-blue-hover disabled:opacity-50">
                  {busy || isRescanning ? (
                    <span className="inline-flex items-center gap-2">
                      <span className="inline-block h-4 w-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                      Scanning…
                    </span>
                  ) : 'Start Scan'}
                </button>
              </div>
            </form>

            {/* Scan progress + log */}
            {isRescanning && (
              <div className="mt-4 border-t border-border pt-4 shrink-0">
                <div className="flex items-center gap-2 text-sm text-muted-foreground mb-2">
                  <span className="inline-block h-4 w-4 border-2 border-foreground/30 border-t-foreground rounded-full animate-spin" />
                  <span>Scanning {scanConfig.network_range}…</span>
                  <span className="ml-auto tabular-nums">{scanProgress.found} found</span>
                </div>
                <div className="flex gap-2 text-xs text-muted-foreground mb-2">
                  <span className="px-1.5 py-0.5 rounded bg-badge-info-bg text-badge-info-fg">SNMP {scanProgress.by_method.snmp}</span>
                  <span className="px-1.5 py-0.5 rounded bg-badge-success-bg text-badge-success-fg">Ping {scanProgress.by_method.ping}</span>
                  <span className="px-1.5 py-0.5 rounded bg-badge-warning-bg text-badge-warning-fg">Port {scanProgress.by_method.port}</span>
                </div>
              </div>
            )}
            {scanLog.length > 0 && (
              <div className="mt-2 flex-1 overflow-y-auto min-h-0 bg-surface-subtle rounded-sm p-2">
                <div className="space-y-1">
                  {scanLog.slice(-20).map((entry, i) => (
                    <div key={i} className="flex items-center gap-2 text-xs px-2 py-1 rounded-sm hover:bg-card">
                      <span className={`inline-block h-2 w-2 rounded-full ${
                        entry.method === 'snmp' ? 'bg-cisco-blue' : entry.method === 'ping' ? 'bg-cisco-green' : 'bg-ibm-yellow'
                      }`} />
                      <span className="font-mono text-foreground tabular-nums">{entry.ip_address}</span>
                      <span className="text-muted-foreground uppercase text-[10px]">{entry.method}</span>
                      {entry.is_new && <span className="ml-auto px-1 text-[10px] rounded bg-badge-success-bg text-badge-success-fg">new</span>}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      <div className="bg-card border border-border rounded-sm overflow-hidden">
        {isLoading ? (
          <div className="px-6 py-12 text-center text-sm text-muted-foreground">Loading devices…</div>
        ) : devices.length === 0 ? (
          <div className="px-6 py-16 text-center">
            <Server className="h-8 w-8 text-muted-foreground mx-auto mb-3 opacity-50" />
            <h3 className="text-sm font-semibold text-foreground">No devices yet</h3>
            <p className="text-xs text-muted-foreground mt-1 max-w-sm mx-auto">
              Scan a network range to discover devices automatically, or add one manually.
            </p>
            <div className="flex justify-center gap-2 mt-4">
              <button
                onClick={() => setShowScanModal(true)}
                className="inline-flex items-center gap-1.5 text-sm px-3 py-1.5 bg-cisco-blue text-white rounded-sm hover:bg-cisco-blue-hover"
              >
                <ScanLine className="h-3.5 w-3.5" />
                Scan network
              </button>
              <button
                onClick={() => setShowAddForm(true)}
                className="inline-flex items-center gap-1.5 text-sm px-3 py-1.5 bg-ibm-purple text-white rounded-sm hover:bg-ibm-purple-hover"
              >
                <Plus className="h-3.5 w-3.5" />
                Add manually
              </button>
            </div>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-border">
              <thead className="bg-surface-subtle">
                <tr>
                  <th scope="col" className="px-4 py-2.5 text-left text-[11px] font-medium text-muted-foreground uppercase tracking-wide">Device</th>
                  <th scope="col" className="px-4 py-2.5 text-left text-[11px] font-medium text-muted-foreground uppercase tracking-wide">IP</th>
                  <th scope="col" className="px-4 py-2.5 text-left text-[11px] font-medium text-muted-foreground uppercase tracking-wide">Status</th>
                  <th scope="col" className="px-4 py-2.5 text-left text-[11px] font-medium text-muted-foreground uppercase tracking-wide hidden md:table-cell">Method</th>
                  <th scope="col" className="px-4 py-2.5 text-left text-[11px] font-medium text-muted-foreground uppercase tracking-wide hidden lg:table-cell">Last polled</th>
                  <th scope="col" className="px-4 py-2.5 text-right text-[11px] font-medium text-muted-foreground uppercase tracking-wide w-px">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {filteredDevices.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-6 py-12 text-center text-sm text-muted-foreground">
                      <Filter className="h-6 w-6 mx-auto mb-2 opacity-50" />
                      No devices match the current filters
                    </td>
                  </tr>
                ) : (
                  filteredDevices.map((device) => {
                    const stale = isStale(device);
                    return (
                      <tr key={device.id} className="hover:bg-surface-hover transition-colors">
                        <td className="px-4 py-2.5">
                          {editingDeviceId === device.id ? (
                            <div className="flex items-center gap-2">
                              <input
                                type="text"
                                value={editName}
                                onChange={(e) => setEditName(e.target.value)}
                                onKeyDown={(e) => {
                                  if (e.key === 'Enter') saveDeviceName(device.id);
                                  if (e.key === 'Escape') cancelEditName();
                                }}
                                autoFocus
                                className="w-full px-2 py-1 text-sm border border-ibm-blue bg-card text-foreground rounded-sm focus:outline-none focus:ring-1 focus:ring-ibm-blue"
                              />
                              <button onClick={() => saveDeviceName(device.id)} className="text-cisco-green hover:text-cisco-green-hover p-0.5" title="Save">
                                <Check className="h-3.5 w-3.5" />
                              </button>
                              <button onClick={cancelEditName} className="text-thinkpad-red hover:text-thinkpad-red-hover p-0.5" title="Cancel">
                                <X className="h-3.5 w-3.5" />
                              </button>
                            </div>
                          ) : (
                            <Link
                              to={`/devices/${device.id}`}
                              className="text-sm font-medium text-foreground truncate max-w-xs hover:text-ibm-blue"
                              title="View device details"
                            >
                              {device.name || <span className="text-muted-foreground italic">unnamed</span>}
                            </Link>
                          )}
                          {device.sys_descr && (
                            <div className="text-xs text-muted-foreground truncate max-w-xs" title={device.sys_descr}>
                              {device.sys_descr}
                            </div>
                          )}
                        </td>
                        <td className="px-4 py-2.5 font-mono text-xs text-foreground whitespace-nowrap">
                          {device.ip_address}
                        </td>
                        <td className="px-4 py-2.5 whitespace-nowrap">
                          <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 text-xs rounded-sm font-medium ${statusBadge(device.status)}`}>
                            <span className={`inline-block h-1.5 w-1.5 rounded-full ${statusDot[device.status] || 'bg-muted-foreground'}`} />
                            {device.status}
                          </span>
                          {stale && (
                            <button
                              onClick={() => setStaleModalDevice(device)}
                              className="ml-1.5 inline-flex items-center gap-0.5 text-[10px] uppercase tracking-wide text-ibm-yellow hover:underline"
                              title="Offline >72h"
                            >
                              <AlertTriangle className="h-2.5 w-2.5" />
                              stale
                            </button>
                          )}
                        </td>
                        <td className="px-4 py-2.5 hidden md:table-cell">
                          <span className="inline-flex px-1.5 py-0.5 text-[10px] uppercase tracking-wide rounded-sm bg-badge-neutral-bg text-badge-neutral-fg font-medium">
                            {device.discovery_method || 'unknown'}
                          </span>
                        </td>
                        <td className="px-4 py-2.5 hidden lg:table-cell text-xs text-muted-foreground whitespace-nowrap">
                          {device.last_polled ? new Date(device.last_polled).toLocaleString() : 'never'}
                        </td>
                        <td className="px-4 py-2.5 text-right whitespace-nowrap">
                          <button
                            onClick={() => startEditName(device)}
                            className="text-muted-foreground hover:text-ibm-blue transition-colors p-1 mr-1"
                            title="Edit device name"
                          >
                            <Pencil className="h-3.5 w-3.5" />
                          </button>
                          <button
                            onClick={() => handleDelete(device.id)}
                            className="text-muted-foreground hover:text-thinkpad-red transition-colors p-1"
                            title="Delete device"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {staleModalDevice && (
        <div className="fixed inset-0 bg-foreground/20 flex items-center justify-center z-50">
          <div className="bg-card border border-border rounded-sm p-6 max-w-md w-full mx-4">
            <div className="flex items-center gap-2 mb-3">
              <AlertTriangle className="h-5 w-5 text-amber-500" />
              <h3 className="font-semibold">Stale device</h3>
            </div>
            <p className="text-sm text-muted-foreground mb-4">
              <span className="font-mono">{staleModalDevice.name || staleModalDevice.ip_address}</span>
              {" "}has been offline for &gt;72h. Mark for removal or keep?
            </p>
            <div className="flex justify-end gap-2">
              <button onClick={() => setStaleModalDevice(null)}
                className="px-3 py-1.5 text-xs rounded border border-input">Cancel</button>
              <button
                onClick={async () => {
                  try {
                    await staleActionMutation.mutateAsync({ id: staleModalDevice.id, action: 'keep' });
                    toast.success('Device kept');
                    setStaleModalDevice(null);
                  } catch { toast.error('Action failed'); }
                }}
                disabled={staleActionMutation.isPending}
                className="px-3 py-1.5 text-xs rounded bg-slate-600 text-white hover:bg-slate-700 disabled:opacity-50"
              >Keep</button>
              <button
                onClick={async () => {
                  try {
                    await staleActionMutation.mutateAsync({ id: staleModalDevice.id, action: 'delete' });
                    toast.success('Device removed');
                    setStaleModalDevice(null);
                  } catch { toast.error('Action failed'); }
                }}
                disabled={staleActionMutation.isPending}
                className="px-3 py-1.5 text-xs rounded bg-red-600 text-white hover:bg-red-700 disabled:opacity-50"
              >Remove</button>
            </div>
          </div>
        </div>
      )}

      {/* Delete confirmation modal */}
      {deleteTargetId && (
        <div className="fixed inset-0 bg-foreground/20 flex items-center justify-center z-50">
          <div className="bg-card border border-border rounded-sm p-6 max-w-sm w-full mx-4">
            <div className="flex items-center gap-2 mb-3">
              <AlertTriangle className="h-5 w-5 text-thinkpad-red" />
              <h3 className="font-semibold text-foreground">Delete Device</h3>
            </div>
            <p className="text-sm text-muted-foreground mb-4">
              Are you sure you want to delete this device? This action cannot be undone.
            </p>
            <div className="flex justify-end gap-2">
              <button onClick={() => setDeleteTargetId(null)}
                className="px-4 py-2 text-sm rounded-sm border border-input text-foreground hover:bg-surface-hover">Cancel</button>
              <button onClick={confirmDelete}
                className="px-4 py-2 text-sm rounded-sm bg-thinkpad-red text-white hover:bg-thinkpad-red-hover">Delete</button>
            </div>
          </div>
        </div>
      )}

      {/* Reset & Rescan confirmation modal */}
      {showResetConfirm && (
        <div className="fixed inset-0 bg-foreground/20 flex items-center justify-center z-50">
          <div className="bg-card border border-border rounded-sm p-6 max-w-md w-full mx-4">
            <div className="flex items-center gap-2 mb-3">
              <AlertTriangle className="h-5 w-5 text-thinkpad-red" />
              <h3 className="font-semibold text-foreground">Reset & Rescan</h3>
            </div>
            <p className="text-sm text-muted-foreground mb-4">
              This will <strong className="text-thinkpad-red">wipe ALL devices and topology</strong>, then scan the current network range. This action cannot be undone.
            </p>
            <div className="flex justify-end gap-2">
              <button onClick={() => setShowResetConfirm(false)}
                className="px-4 py-2 text-sm rounded-sm border border-input text-foreground hover:bg-surface-hover">Cancel</button>
              <button onClick={confirmResetRescan}
                className="px-4 py-2 text-sm rounded-sm bg-thinkpad-red text-white hover:bg-thinkpad-red-hover">Reset & Rescan</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default Devices;