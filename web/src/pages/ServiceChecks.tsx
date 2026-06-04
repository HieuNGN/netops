import { useState } from 'react';
import { Plus, Play, Trash2 } from 'lucide-react';
import { useChecks, useCheckResults } from '../hooks/useChecks';
import { useToast } from '../components/ui';

const CHECK_TYPES = [
  { value: 'http', label: 'HTTP/HTTPS' },
  { value: 'tcp', label: 'TCP Port' },
  { value: 'dns', label: 'DNS' },
  { value: 'ping', label: 'Ping' },
  { value: 'ssl', label: 'SSL Certificate' },
];

export function ServiceChecks() {
  const { checks, isLoading, createCheck, deleteCheck, runCheck } = useChecks();
  const toast = useToast();
  const [showAddForm, setShowAddForm] = useState(false);
  const [selectedCheckId, setSelectedCheckId] = useState<string | null>(null);
  const [newCheck, setNewCheck] = useState({
    name: '',
    check_type: 'http',
    target: '',
    interval_seconds: 60,
    timeout_seconds: 10,
    config: {},
    enabled: true,
  });

  const { results: checkResults, isLoading: resultsLoading } = useCheckResults(
    selectedCheckId || ''
  );

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    let config = {};
    switch (newCheck.check_type) {
      case 'http':
        config = { url: newCheck.target, method: 'GET', expected_status: [200] };
        break;
      case 'tcp':
        const [tcpHost, tcpPort] = newCheck.target.split(':');
        config = { host: tcpHost, port: parseInt(tcpPort) || 80 };
        break;
      case 'dns':
        config = { domain: newCheck.target, record_type: 'A' };
        break;
      case 'ping':
        config = { host: newCheck.target, count: 3 };
        break;
      case 'ssl':
        const [sslHost] = newCheck.target.split(':');
        config = { host: sslHost, port: 443, warning_days: 30, critical_days: 7 };
        break;
    }

    try {
      await createCheck({ ...newCheck, config });
      toast.success('Service check created successfully', newCheck.name);
      setNewCheck({
        name: '',
        check_type: 'http',
        target: '',
        interval_seconds: 60,
        timeout_seconds: 10,
        config: {},
        enabled: true,
      });
      setShowAddForm(false);
    } catch (error) {
      toast.error('Failed to create service check', 'Error');
    }
  };

  const handleRunNow = async (id: string) => {
    try {
      const result = await runCheck(id);
      toast.info(result.data.message || `Status: ${result.data.status}`, 'Check Result');
    } catch (error) {
      toast.error('Failed to run check', 'Error');
    }
  };

  const handleDelete = async (id: string) => {
    if (confirm('Are you sure you want to delete this check?')) {
      try {
        await deleteCheck(id);
        toast.success('Service check deleted successfully');
        if (selectedCheckId === id) setSelectedCheckId(null);
      } catch (error) {
        toast.error('Failed to delete check', 'Error');
      }
    }
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-6 gap-4">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Service Checks</h1>
          <p className="text-muted-foreground mt-1">Monitor HTTP, TCP, DNS, Ping, and SSL endpoints</p>
        </div>
        <button
          onClick={() => setShowAddForm(true)}
          className="flex items-center space-x-2 px-4 py-2 bg-btn-primary text-btn-primary-foreground rounded-sm hover:bg-btn-primary-hover"
        >
          <Plus className="h-4 w-4" />
          <span>Add Check</span>
        </button>
      </div>

      {showAddForm && (
        <div className="mb-6 bg-card rounded-sm shadow-sm border border-border p-6">
          <h2 className="text-lg font-semibold text-foreground mb-4">Add New Service Check</h2>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">Name *</label>
                <input
                  type="text"
                  value={newCheck.name}
                  onChange={(e) => setNewCheck({ ...newCheck, name: e.target.value })}
                  className="w-full px-3 py-2 border border-input dark:border-input bg-card text-foreground rounded-sm focus:ring-1 focus:ring-ring"
                  placeholder="Google Homepage"
                  required
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">Check Type *</label>
                <select
                  value={newCheck.check_type}
                  onChange={(e) => setNewCheck({ ...newCheck, check_type: e.target.value })}
                  className="w-full px-3 py-2 border border-input dark:border-input bg-card text-foreground rounded-sm focus:ring-1 focus:ring-ring"
                >
                  {CHECK_TYPES.map((type) => (
                    <option key={type.value} value={type.value} className="bg-card">
                      {type.label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="md:col-span-2">
                <label className="block text-sm font-medium text-foreground mb-1">Target *</label>
                <input
                  type="text"
                  value={newCheck.target}
                  onChange={(e) => setNewCheck({ ...newCheck, target: e.target.value })}
                  className="w-full px-3 py-2 border border-input dark:border-input bg-card text-foreground rounded-sm focus:ring-1 focus:ring-ring"
                  placeholder={
                    newCheck.check_type === 'http'
                      ? 'https://example.com'
                      : newCheck.check_type === 'tcp'
                      ? 'host:port'
                      : newCheck.check_type === 'dns'
                      ? 'example.com'
                      : newCheck.check_type === 'ssl'
                      ? 'example.com:443'
                      : '192.168.1.1'
                  }
                  required
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">
                  Interval (seconds)
                </label>
                <input
                  type="number"
                  value={newCheck.interval_seconds}
                  onChange={(e) =>
                    setNewCheck({ ...newCheck, interval_seconds: parseInt(e.target.value) })
                  }
                  className="w-full px-3 py-2 border border-input dark:border-input bg-card text-foreground rounded-sm focus:ring-1 focus:ring-ring"
                  min="10"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">
                  Timeout (seconds)
                </label>
                <input
                  type="number"
                  value={newCheck.timeout_seconds}
                  onChange={(e) =>
                    setNewCheck({ ...newCheck, timeout_seconds: parseInt(e.target.value) })
                  }
                  className="w-full px-3 py-2 border border-input dark:border-input bg-card text-foreground rounded-sm focus:ring-1 focus:ring-ring"
                  min="1"
                  max="60"
                />
              </div>
            </div>
            <div className="flex justify-end space-x-2">
              <button
                type="button"
                onClick={() => setShowAddForm(false)}
                className="px-4 py-2 text-foreground bg-secondary rounded-sm hover:bg-surface-hover"
              >
                Cancel
              </button>
              <button
                type="submit"
                className="px-4 py-2 bg-btn-primary text-btn-primary-foreground rounded-sm hover:bg-btn-primary-hover"
              >
                Add Check
              </button>
            </div>
          </form>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 bg-card rounded-sm shadow-sm border border-border overflow-hidden">
          <div className="px-6 py-4 border-b border-border">
            <h2 className="text-lg font-semibold text-foreground">Configured Checks</h2>
          </div>
          <div className="divide-y divide-border">
            {isLoading ? (
              <div className="px-6 py-8 text-center text-muted-foreground">Loading checks...</div>
            ) : checks.length === 0 ? (
              <div className="px-6 py-8 text-center text-muted-foreground">
                No service checks configured. Add your first check above.
              </div>
            ) : (
              checks.map((check) => (
                <div
                  key={check.id}
                  className={`px-6 py-4 hover:bg-muted dark:hover:bg-muted cursor-pointer ${
                    selectedCheckId === check.id ? 'bg-surface-subtle' : ''
                  }`}
                  onClick={() => setSelectedCheckId(check.id)}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex-1">
                      <div className="flex items-center space-x-3">
                        <span className="font-medium text-foreground">{check.name}</span>
                        <span className="px-2 py-0.5 bg-badge-neutral-bg text-badge-neutral-fg text-xs rounded uppercase">
                          {check.check_type}
                        </span>
              {!check.enabled && (
                <span className="px-2 py-0.5 bg-badge-warning-bg text-badge-warning-fg text-xs rounded">
                  Disabled
                </span>
              )}
                      </div>
                      <p className="text-sm text-muted-foreground mt-1 font-mono">{check.target}</p>
                      <p className="text-xs text-muted-foreground mt-1">
                        Every {check.interval_seconds}s • Timeout: {check.timeout_seconds}s
                      </p>
                    </div>
                    <div className="flex items-center space-x-2">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleRunNow(check.id);
                        }}
                        className="p-2 text-muted-foreground hover:bg-surface-hover rounded-sm"
                        title="Run now"
                      >
                        <Play className="h-4 w-4" />
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleDelete(check.id);
                        }}
                        className="p-2 text-destructive hover:bg-badge-destructive-bg rounded-sm"
                        title="Delete"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        <div className="bg-card rounded-sm shadow-sm border border-border overflow-hidden">
          <div className="px-6 py-4 border-b border-border">
            <h2 className="text-lg font-semibold text-foreground">Check Results</h2>
          </div>
          <div className="p-6">
            {!selectedCheckId ? (
              <p className="text-muted-foreground text-sm">Select a check to view results</p>
            ) : resultsLoading ? (
              <p className="text-muted-foreground text-sm">Loading results...</p>
            ) : checkResults.length === 0 ? (
              <p className="text-muted-foreground text-sm">No results yet for this check</p>
            ) : (
              <div className="space-y-3 max-h-96 overflow-y-auto">
                {checkResults.slice(0, 10).map((result, idx) => (
                  <div
                    key={idx}
                    className="p-3 bg-surface-subtle rounded-sm border border-border"
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span
                        className={`px-2 py-0.5 text-xs rounded font-medium ${
                        result.status === 'up'
                          ? 'bg-badge-success-bg text-badge-success-fg'
                          : result.status === 'down'
                          ? 'bg-badge-destructive-bg text-badge-destructive-fg'
                          : 'bg-badge-warning-bg text-badge-warning-fg'
                        }`}
                      >
                        {result.status}
                      </span>
                      <span className="text-xs text-muted-foreground">
                        {result.response_time_ms.toFixed(0)}ms
                      </span>
                    </div>
                    <p className="text-sm text-foreground">{result.message}</p>
                    {result.error && (
                      <p className="text-xs text-destructive mt-1">{result.error}</p>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default ServiceChecks;