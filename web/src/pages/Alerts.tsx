import { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Plus, Trash2, Send, Clock, Bell, Check, X, Pencil, AlertCircle } from 'lucide-react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { alertsApi, integrationsApi, maintenanceWindowsApi } from '../api';
import type { IntegrationConfig, IntegrationType } from '../api/endpoints';
import { useActiveAlerts } from '../hooks/useActiveAlerts';
import { useToast } from '../components/ui';

const ALERT_TYPES = [
  'device_down',
  'device_up',
  'link_down',
  'topology_change',
  'check_down',
  'check_degraded',
];

const CHANNELS: { value: IntegrationType; label: string; fields: { key: string; label: string; placeholder?: string; secret?: boolean }[]; supportsIntegration: boolean }[] = [
  {
    value: 'webhook',
    label: 'Webhook',
    supportsIntegration: true,
    fields: [{ key: 'url', label: 'Webhook URL', placeholder: 'https://example.com/hook' }],
  },
  {
    value: 'slack',
    label: 'Slack',
    supportsIntegration: true,
    fields: [{ key: 'webhook_url', label: 'Slack Webhook URL', placeholder: 'https://hooks.slack.com/services/...' }],
  },
  {
    value: 'telegram',
    label: 'Telegram',
    supportsIntegration: true,
    fields: [
      { key: 'chat_id', label: 'Chat ID', placeholder: '-1001234567890' },
    ],
  },
  {
    value: 'whatsapp',
    label: 'WhatsApp',
    supportsIntegration: true,
    fields: [
      { key: 'to_number', label: 'Recipient WhatsApp Number', placeholder: '+15551234567' },
    ],
  },
  {
    value: 'email',
    label: 'Email',
    supportsIntegration: true,
    fields: [
      { key: 'recipients', label: 'Recipients (comma-separated)', placeholder: 'ops@example.com' },
    ],
  },
];

export function Alerts() {
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();

  const tabParam = searchParams.get('tab');
  const initialTab: 'active' | 'rules' | 'windows' =
    tabParam === 'rules' || tabParam === 'windows' ? tabParam : 'active';
  const [activeTab, setActiveTab] = useState<'active' | 'rules' | 'windows'>(initialTab);
  const [showAddForm, setShowAddForm] = useState(false);
  const [editingAlertId, setEditingAlertId] = useState<string | null>(null);
  const emptyForm = {
    name: '',
    alert_type: 'device_down',
    channel: 'webhook' as IntegrationType,
    config: {} as Record<string, string>,
    integration_id: null as string | null,
    enabled: true,
  };
  const [newAlert, setNewAlert] = useState({ ...emptyForm });

  // Legacy deep-link from older PostSignupBanner. New flow goes through
  // /settings?focus=integrations so users set up credentials first.
  const focusChannel = searchParams.get('focus') === 'channel';
  const derivedTab: 'active' | 'rules' | 'windows' = focusChannel ? 'rules' : activeTab;
  const derivedShowAdd = focusChannel || showAddForm;

  useEffect(() => {
    if (searchParams.has('focus')) {
      const next = new URLSearchParams(searchParams);
      next.delete('focus');
      setSearchParams(next, { replace: true });
    }
  }, [searchParams, setSearchParams]);

  const switchTab = (t: 'active' | 'rules' | 'windows') => {
    setActiveTab(t);
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      if (t === 'active') next.delete('tab');
      else next.set('tab', t);
      return next;
    }, { replace: true });
  };

  const { data: alerts = [], isLoading } = useQuery({
    queryKey: ['alerts'],
    queryFn: async () => {
      const response = await alertsApi.list();
      return response.data;
    },
  });

  const { data: allIntegrations = [] } = useQuery({
    queryKey: ['integrations'],
    queryFn: async () => (await integrationsApi.list()).data,
  });

  const integrationsForChannel = (channel: IntegrationType) =>
    allIntegrations.filter((i) => i.type === channel);

  const createMutation = useMutation({
    mutationFn: (data: any) => alertsApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alerts'] });
      resetForm();
      toast.success('Alert rule created', newAlert.name);
    },
    onError: handleMutationError,
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: any }) => alertsApi.update(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alerts'] });
      resetForm();
      toast.success('Alert rule updated', newAlert.name);
    },
    onError: handleMutationError,
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => alertsApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alerts'] });
      toast.success('Alert rule deleted');
    },
    onError: (e: any) => {
      toast.error(e?.response?.data?.detail || 'Delete failed');
    },
  });

  const {
    alerts: activeAlerts,
    isLoading: activeAlertsLoading,
    acknowledge,
    resolve,
  } = useActiveAlerts();

  const toast = useToast();

  const testMutation = useMutation({
    mutationFn: (id: string) => alertsApi.test(id),
    onSuccess: (resp) => {
      if (resp.data.sent) toast.success('Test alert sent');
      else toast.error('Test failed — check channel config');
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail || 'Test failed'),
  });

  function resetForm() {
    setNewAlert({ ...emptyForm });
    setShowAddForm(false);
    setEditingAlertId(null);
  }

  function startEdit(alert: any) {
    setNewAlert({
      name: alert.name,
      alert_type: alert.alert_type,
      channel: alert.channel,
      config: alert.config_json || {},
      integration_id: alert.integration_id,
      enabled: alert.enabled,
    });
    setEditingAlertId(alert.id);
    setShowAddForm(true);
  }

  function handleMutationError(e: any) {
    if (e?.response?.status === 409) {
      const detail = e.response.data?.detail;
      const name = detail?.existing_name || 'existing rule';
      toast.error(
        `Duplicate: rule "${name}" already covers this alert type, channel, and config. Edit that one instead.`,
      );
    } else {
      toast.error(e?.response?.data?.detail || e?.message || 'Request failed');
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    // Strip empty config values
    const cleanedConfig: Record<string, string> = {};
    Object.entries(newAlert.config || {}).forEach(([k, v]) => {
      if (v !== '' && v != null) cleanedConfig[k] = v;
    });
    const payload = {
      name: newAlert.name,
      alert_type: newAlert.alert_type,
      channel: newAlert.channel,
      config: cleanedConfig,
      integration_id: newAlert.integration_id,
      enabled: newAlert.enabled,
    };
    if (editingAlertId) {
      updateMutation.mutate({ id: editingAlertId, data: payload });
    } else {
      createMutation.mutate(payload);
    }
  };

  const handleChannelChange = (channel: IntegrationType) => {
    setNewAlert({
      ...newAlert,
      channel,
      config: {},
      integration_id: null,
    });
  };

  const handleTest = (id: string) => {
    testMutation.mutate(id);
  };

  // Maintenance Windows
  const { data: windows = [], isLoading: windowsLoading } = useQuery({
    queryKey: ['maintenanceWindows'],
    queryFn: async () => {
      const response = await maintenanceWindowsApi.list();
      return response.data.windows;
    },
  });

  const [showWindowForm, setShowWindowForm] = useState(false);
  const [newWindow, setNewWindow] = useState({
    name: '',
    start_time: '',
    end_time: '',
    description: '',
  });

  const createWindowMutation = useMutation({
    mutationFn: (data: any) => maintenanceWindowsApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['maintenanceWindows'] });
      setShowWindowForm(false);
    },
  });

  const deleteWindowMutation = useMutation({
    mutationFn: (id: string) => maintenanceWindowsApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['maintenanceWindows'] });
    },
  });

  const handleWindowSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await createWindowMutation.mutateAsync(newWindow);
      toast.success('Maintenance window created');
      setNewWindow({ name: '', start_time: '', end_time: '', description: '' });
    } catch (error) {
      toast.error('Failed to create maintenance window', 'Error');
    }
  };

  const isWindowActive = (start: string, end: string) => {
    const now = new Date();
    const s = new Date(start);
    const e = new Date(end);
    return now >= s && now <= e;
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-6 gap-4">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Alerts</h1>
          <p className="text-muted-foreground mt-1">Configure alert rules and notifications</p>
        </div>
        {derivedTab === 'rules' && (
          <button
            onClick={() => setShowAddForm(true)}
            className="flex items-center space-x-2 px-4 py-2 bg-btn-primary text-btn-primary-foreground rounded-sm hover:bg-btn-primary-hover"
          >
            <Plus className="h-4 w-4" />
            <span>Add Alert</span>
          </button>
        )}
        {derivedTab === 'windows' && (
          <button
            onClick={() => setShowWindowForm(true)}
            className="flex items-center space-x-2 px-4 py-2 bg-btn-primary text-btn-primary-foreground rounded-sm hover:bg-btn-primary-hover"
          >
            <Plus className="h-4 w-4" />
            <span>Add Window</span>
          </button>
        )}
      </div>

      {/* Tabs */}
      <div className="mb-6 border-b border-border">
        <nav className="-mb-px flex space-x-8">
          <button
            onClick={() => switchTab('active')}
            className={`flex items-center space-x-2 py-4 px-1 border-b-2 font-medium text-sm ${
              derivedTab === 'active'
                ? 'border-destructive text-destructive'
                : 'border-transparent text-muted-foreground hover:text-foreground dark:hover:text-foreground'
            }`}
          >
            <Bell className="h-4 w-4" />
            <span>Active Alerts</span>
            {activeAlerts.length > 0 && (
              <span className="ml-1.5 px-1.5 py-0.5 bg-btn-destructive text-btn-destructive-foreground text-xs rounded-sm font-medium">
                {activeAlerts.length}
              </span>
            )}
          </button>
          <button
            onClick={() => switchTab('rules')}
            className={`flex items-center space-x-2 py-4 px-1 border-b-2 font-medium text-sm ${
              derivedTab === 'rules'
                ? 'border-destructive text-destructive'
                : 'border-transparent text-muted-foreground hover:text-foreground dark:hover:text-foreground'
            }`}
          >
            <Bell className="h-4 w-4" />
            <span>Alert Rules</span>
          </button>
          <button
            onClick={() => switchTab('windows')}
            className={`flex items-center space-x-2 py-4 px-1 border-b-2 font-medium text-sm ${
              derivedTab === 'windows'
                ? 'border-destructive text-destructive'
                : 'border-transparent text-muted-foreground hover:text-foreground dark:hover:text-foreground'
            }`}
          >
            <Clock className="h-4 w-4" />
            <span>Maintenance Windows</span>
          </button>
        </nav>
      </div>

      {derivedTab === 'rules' && (
        <>
          {/* Add/Edit Alert Form */}
          {derivedShowAdd && (
            <div className="mb-6 bg-card rounded-sm shadow-sm border border-border p-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-semibold text-foreground">
                  {editingAlertId ? 'Edit Alert Rule' : 'Add Alert Rule'}
                </h2>
                <button
                  type="button"
                  onClick={resetForm}
                  className="text-muted-foreground hover:text-foreground"
                  aria-label="Close form"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
              <form onSubmit={handleSubmit} className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-foreground mb-1">Name *</label>
                    <input
                      type="text"
                      value={newAlert.name}
                      onChange={(e) => setNewAlert({ ...newAlert, name: e.target.value })}
                      className="w-full px-3 py-2 border border-input dark:border-input bg-card text-foreground rounded-sm focus:ring-1 focus:ring-destructive"
                      placeholder="Device Down Alert"
                      required
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-foreground mb-1">Alert Type *</label>
                    <select
                      value={newAlert.alert_type}
                      onChange={(e) => setNewAlert({ ...newAlert, alert_type: e.target.value })}
                      className="w-full px-3 py-2 border border-input dark:border-input bg-card text-foreground rounded-sm focus:ring-1 focus:ring-destructive"
                    >
                      {ALERT_TYPES.map((type) => (
                        <option key={type} value={type} className="bg-card">
                          {type}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-foreground mb-1">Channel *</label>
                    <select
                      value={newAlert.channel}
                      onChange={(e) => handleChannelChange(e.target.value as IntegrationType)}
                      className="w-full px-3 py-2 border border-input dark:border-input bg-card text-foreground rounded-sm focus:ring-1 focus:ring-destructive"
                    >
                      {CHANNELS.map((c) => (
                        <option key={c.value} value={c.value} className="bg-card">
                          {c.label}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-foreground mb-1">Enabled</label>
                    <label className="flex items-center space-x-2 px-3 py-2 border border-input bg-card rounded-sm">
                      <input
                        type="checkbox"
                        checked={newAlert.enabled}
                        onChange={(e) => setNewAlert({ ...newAlert, enabled: e.target.checked })}
                      />
                      <span className="text-sm text-foreground">
                        {newAlert.enabled ? 'Enabled' : 'Disabled'}
                      </span>
                    </label>
                  </div>
                </div>

                {(() => {
                  const channel = CHANNELS.find((c) => c.value === newAlert.channel);
                  if (!channel) return null;
                  const available = integrationsForChannel(newAlert.channel);
                  return (
                    <div className="bg-surface-subtle p-4 rounded-sm space-y-3">
                      {channel.supportsIntegration && (
                        <div>
                          <label className="block text-sm font-medium text-foreground mb-1">
                            Use Integration
                            <span className="text-xs text-muted-foreground ml-2">
                              (optional — credentials from Settings)
                            </span>
                          </label>
                          <select
                            value={newAlert.integration_id || ''}
                            onChange={(e) =>
                              setNewAlert({
                                ...newAlert,
                                integration_id: e.target.value || null,
                              })
                            }
                            className="w-full px-3 py-2 border border-input bg-card text-foreground rounded-sm focus:ring-1 focus:ring-destructive"
                          >
                            <option value="">— None (configure inline below) —</option>
                            {available.map((integ) => (
                              <option key={integ.id} value={integ.id} className="bg-card">
                                {integ.name}
                              </option>
                            ))}
                          </select>
                          {available.length === 0 && (
                            <p className="text-xs text-muted-foreground mt-1">
                              No {channel.label} integrations yet. Add one in Settings → Integrations.
                            </p>
                          )}
                        </div>
                      )}
                      {!newAlert.integration_id && channel.fields.length > 0 && (
                        <div>
                          <p className="text-sm font-medium text-foreground mb-2">
                            Inline channel config
                          </p>
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                            {channel.fields.map((field) => (
                              <div key={field.key}>
                                <label className="block text-xs font-medium text-muted-foreground mb-1">
                                  {field.label}
                                </label>
                                <input
                                  type={field.secret ? 'password' : 'text'}
                                  value={newAlert.config[field.key] || ''}
                                  onChange={(e) =>
                                    setNewAlert({
                                      ...newAlert,
                                      config: {
                                        ...newAlert.config,
                                        [field.key]: e.target.value,
                                      },
                                    })
                                  }
                                  placeholder={field.placeholder}
                                  className="w-full px-3 py-2 border border-input bg-card text-foreground rounded-sm focus:ring-1 focus:ring-destructive"
                                />
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                      {newAlert.integration_id && (
                        <p className="text-xs text-muted-foreground">
                          Credentials pulled from the selected integration. Per-rule overrides below will take precedence.
                        </p>
                      )}
                    </div>
                  );
                })()}

                <div className="flex justify-end space-x-2">
                  <button
                    type="button"
                    onClick={resetForm}
                    className="px-4 py-2 bg-secondary text-secondary-foreground hover:bg-surface-hover rounded-sm"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={createMutation.isPending || updateMutation.isPending}
                    className="px-4 py-2 bg-btn-primary text-btn-primary-foreground rounded-sm hover:bg-btn-primary-hover disabled:opacity-50"
                  >
                    {editingAlertId
                      ? (updateMutation.isPending ? 'Saving...' : 'Save Changes')
                      : (createMutation.isPending ? 'Creating...' : 'Create Alert')}
                  </button>
                </div>
              </form>
            </div>
          )}

          {/* Alerts List */}
          <div className="bg-card rounded-sm shadow-sm border border-border overflow-hidden">
            <div className="px-6 py-4 border-b border-border">
              <h2 className="text-lg font-semibold text-foreground">Alert Rules</h2>
            </div>
            <div className="divide-y divide-border">
              {isLoading ? (
                <div className="px-6 py-8 text-center text-muted-foreground">Loading alerts...</div>
              ) : alerts.length === 0 ? (
                <div className="px-6 py-8 text-center text-muted-foreground">
                  No alert rules configured. Add your first alert above.
                </div>
              ) : (
                alerts.map((alert) => {
                  const linkedInteg = allIntegrations.find((i) => i.id === alert.integration_id);
                  return (
                  <div key={alert.id} className="px-6 py-4 hover:bg-muted dark:hover:bg-muted">
                    <div className="flex items-center justify-between">
                      <div className="flex-1">
                        <div className="flex items-center space-x-3">
                          <span className="font-medium text-foreground">{alert.name}</span>
                          <span className="px-2 py-0.5 bg-badge-neutral-bg text-badge-neutral-fg text-xs rounded">
                            {alert.alert_type}
                          </span>
                          <span className="px-2 py-0.5 bg-badge-neutral-bg text-badge-neutral-fg text-xs rounded">
                            {alert.channel}
                          </span>
                          {linkedInteg && (
                            <span
                              className="px-2 py-0.5 bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300 text-xs rounded inline-flex items-center space-x-1"
                              title={`Uses integration: ${linkedInteg.name}`}
                            >
                              <AlertCircle className="h-3 w-3" />
                              <span>{linkedInteg.name}</span>
                            </span>
                          )}
                          {!alert.enabled && (
                  <span className="px-2 py-0.5 bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400 text-xs rounded">
                    Disabled
                  </span>
                          )}
                        </div>
                      </div>
                      <div className="flex items-center space-x-2">
                        <button
                          onClick={() => handleTest(alert.id)}
                          className="p-2 text-muted-foreground hover:bg-surface-hover rounded-sm"
                          title="Test alert"
                        >
                          <Send className="h-4 w-4" />
                        </button>
                        <button
                          onClick={() => startEdit(alert)}
                          className="p-2 text-muted-foreground hover:bg-surface-hover rounded-sm"
                          title="Edit"
                        >
                          <Pencil className="h-4 w-4" />
                        </button>
                        <button
                          onClick={() => {
                            if (confirm(`Delete alert rule "${alert.name}"?`)) {
                              deleteMutation.mutate(alert.id);
                            }
                          }}
                          className="p-2 text-destructive hover:bg-badge-destructive-bg rounded-sm"
                          title="Delete"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                    </div>
                  </div>
                  );
                })
              )}
            </div>
          </div>
        </>
      )}

      {derivedTab === 'active' && (
        <div className="bg-card rounded-sm shadow-sm border border-border overflow-hidden">
          <div className="px-6 py-4 border-b border-border flex justify-between items-center">
            <h2 className="text-lg font-semibold text-foreground">Active Alerts</h2>
            <span className="text-sm text-muted-foreground">Refreshes every 15s</span>
          </div>
          <div className="divide-y divide-border">
            {activeAlertsLoading ? (
              <div className="px-6 py-8 text-center text-muted-foreground">Loading alerts...</div>
            ) : activeAlerts.length === 0 ? (
              <div className="px-6 py-8 text-center text-muted-foreground">
                No active alerts. All systems clear.
              </div>
            ) : (
              activeAlerts.map((alert) => (
                <div
                  key={alert.key}
                  className={`px-6 py-4 flex items-center justify-between ${
                    alert.status === 'firing'
                      ? 'bg-destructive/10 dark:bg-destructive/20'
                      : 'bg-badge-warning-bg'
                  }`}
                >
                  <div className="flex items-start space-x-3">
                    <div className="mt-0.5">
                    <span
                      className={`inline-flex px-2 py-0.5 text-xs rounded-sm font-medium ${
                        alert.severity === 'critical'
                          ? 'bg-btn-destructive text-btn-destructive-foreground'
                          : alert.severity === 'warning'
                          ? 'bg-warning text-warning-foreground'
                          : 'bg-gray-100 text-gray-700 dark:bg-muted dark:text-muted-foreground'
                      }`}
                    >
                      {alert.severity}
                    </span>
                    </div>
                    <div>
                      <p className="text-sm font-medium text-foreground">{alert.title}</p>
                      <p className="text-xs text-muted-foreground">{alert.message}</p>
                      <p className="text-xs text-muted-foreground mt-0.5">
                        {alert.status === 'acknowledged' && (
                          <span className="text-warning-foreground font-medium">Acknowledged · </span>
                        )}
                        Fired {new Date(alert.fired_at * 1000).toLocaleTimeString()}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center space-x-1">
                    {alert.status === 'firing' && (
                      <button
                        onClick={() => acknowledge(alert.key)}
                        className="p-1.5 text-muted-foreground hover:bg-surface-hover rounded-sm"
                        title="Acknowledge"
                      >
                        <Check className="h-4 w-4" />
                      </button>
                    )}
                    <button
                      onClick={() => resolve(alert.key)}
                      className="p-1.5 text-destructive hover:bg-badge-destructive-bg rounded-sm"
                      title="Resolve"
                    >
                      <X className="h-4 w-4" />
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      )}

      {derivedTab === 'windows' && (
        <>
          {/* Add Maintenance Window Form */}
          {showWindowForm && (
            <div className="mb-6 bg-card rounded-sm shadow-sm border border-border p-6">
              <h2 className="text-lg font-semibold text-foreground mb-4">Add Maintenance Window</h2>
              <form onSubmit={handleWindowSubmit} className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="md:col-span-2">
                    <label className="block text-sm font-medium text-foreground mb-1">Name *</label>
                    <input
                      type="text"
                      value={newWindow.name}
                      onChange={(e) => setNewWindow({ ...newWindow, name: e.target.value })}
                      className="w-full px-3 py-2 border border-input dark:border-input bg-card text-foreground rounded-sm focus:ring-1 focus:ring-destructive"
                      placeholder="Scheduled Maintenance"
                      required
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-foreground mb-1">Start Time *</label>
                    <input
                      type="datetime-local"
                      value={newWindow.start_time}
                      onChange={(e) => setNewWindow({ ...newWindow, start_time: e.target.value })}
                      className="w-full px-3 py-2 border border-input dark:border-input bg-card text-foreground rounded-sm focus:ring-1 focus:ring-destructive"
                      required
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-foreground mb-1">End Time *</label>
                    <input
                      type="datetime-local"
                      value={newWindow.end_time}
                      onChange={(e) => setNewWindow({ ...newWindow, end_time: e.target.value })}
                      className="w-full px-3 py-2 border border-input dark:border-input bg-card text-foreground rounded-sm focus:ring-1 focus:ring-destructive"
                      required
                    />
                  </div>
                  <div className="md:col-span-2">
                    <label className="block text-sm font-medium text-foreground mb-1">Description</label>
                    <textarea
                      value={newWindow.description}
                      onChange={(e) => setNewWindow({ ...newWindow, description: e.target.value })}
                      className="w-full px-3 py-2 border border-input dark:border-input bg-card text-foreground rounded-sm focus:ring-1 focus:ring-destructive"
                      rows={3}
                      placeholder="Planned network maintenance window"
                    />
                  </div>
                </div>
                <div className="flex justify-end space-x-2">
                  <button
                    type="button"
                    onClick={() => setShowWindowForm(false)}
                    className="px-4 py-2 bg-secondary text-secondary-foreground hover:bg-surface-hover rounded-sm"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={createWindowMutation.isPending}
                    className="px-4 py-2 bg-btn-primary text-btn-primary-foreground rounded-sm hover:bg-btn-primary-hover disabled:opacity-50"
                  >
                    {createWindowMutation.isPending ? 'Creating...' : 'Create Window'}
                  </button>
                </div>
              </form>
            </div>
          )}

          {/* Maintenance Windows List */}
          <div className="bg-card rounded-sm shadow-sm border border-border overflow-hidden">
            <div className="px-6 py-4 border-b border-border">
              <h2 className="text-lg font-semibold text-foreground">Maintenance Windows</h2>
            </div>
            <div className="divide-y divide-border">
              {windowsLoading ? (
                <div className="px-6 py-8 text-center text-muted-foreground">Loading windows...</div>
              ) : windows.length === 0 ? (
                <div className="px-6 py-8 text-center text-muted-foreground">
                  No maintenance windows configured. Add a window to suppress alerts during planned downtime.
                </div>
              ) : (
                windows.map((window) => {
                  const active = isWindowActive(window.start_time, window.end_time);
                  return (
                    <div key={window.id} className="px-6 py-4 hover:bg-muted dark:hover:bg-muted">
                      <div className="flex items-center justify-between">
                        <div className="flex-1">
                          <div className="flex items-center space-x-3">
                            <span className="font-medium text-foreground">{window.name}</span>
                            {active && (
                          <span className="px-2 py-0.5 bg-badge-success-bg text-badge-success-fg text-xs rounded font-medium">
                            Active
                          </span>
                            )}
                          </div>
                          <p className="text-sm text-muted-foreground mt-1">
                            {new Date(window.start_time).toLocaleString()} — {new Date(window.end_time).toLocaleString()}
                          </p>
                          {window.description && (
                            <p className="text-xs text-muted-foreground mt-1">{window.description}</p>
                          )}
                        </div>
                        <button
                          onClick={() => deleteWindowMutation.mutate(window.id)}
                          className="p-2 text-destructive hover:bg-badge-destructive-bg rounded-sm"
                          title="Delete"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

export default Alerts;