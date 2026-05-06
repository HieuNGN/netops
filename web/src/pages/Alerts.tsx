import { useState } from 'react';
import { Plus, Trash2, Send, Clock, Bell, Check, X } from 'lucide-react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { alertsApi, maintenanceWindowsApi } from '../api';
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

const CHANNELS = [
  { value: 'webhook', label: 'Webhook' },
  { value: 'slack', label: 'Slack' },
  { value: 'telegram', label: 'Telegram' },
  { value: 'whatsapp', label: 'WhatsApp' },
  { value: 'email', label: 'Email' },
];

export function Alerts() {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<'rules' | 'active' | 'windows'>('active');
  const [showAddForm, setShowAddForm] = useState(false);
  const [newAlert, setNewAlert] = useState({
    name: '',
    alert_type: 'device_down',
    channel: 'webhook',
    config: {},
    enabled: true,
  });

  const { data: alerts = [], isLoading } = useQuery({
    queryKey: ['alerts'],
    queryFn: async () => {
      const response = await alertsApi.list();
      return response.data;
    },
  });

  const createMutation = useMutation({
    mutationFn: (data: any) => alertsApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alerts'] });
      setShowAddForm(false);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => alertsApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alerts'] });
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
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await createMutation.mutateAsync(newAlert);
      toast.success('Alert rule created successfully', newAlert.name);
      setNewAlert({
        name: '',
        alert_type: 'device_down',
        channel: 'webhook',
        config: {},
        enabled: true,
      });
    } catch (error) {
      toast.error('Failed to create alert rule', 'Error');
    }
  };

  const handleTest = async (id: string) => {
    try {
      await testMutation.mutateAsync(id);
      toast.success('Test alert sent successfully');
    } catch (error) {
      toast.error('Failed to send test alert', 'Error');
    }
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
          <h1 className="text-2xl font-bold text-[#161616] dark:text-white">Alerts</h1>
          <p className="text-[#525252] dark:text-[#a8a8a8] mt-1">Configure alert rules and notifications</p>
        </div>
        {activeTab === 'rules' && (
          <button
            onClick={() => setShowAddForm(true)}
            className="flex items-center space-x-2 px-4 py-2 bg-[#161616] text-white rounded-sm hover:bg-[#525252]"
          >
            <Plus className="h-4 w-4" />
            <span>Add Alert</span>
          </button>
        )}
        {activeTab === 'windows' && (
          <button
            onClick={() => setShowWindowForm(true)}
            className="flex items-center space-x-2 px-4 py-2 bg-[#161616] text-white rounded-sm hover:bg-[#525252]"
          >
            <Plus className="h-4 w-4" />
            <span>Add Window</span>
          </button>
        )}
      </div>

      {/* Tabs */}
      <div className="mb-6 border-b border-[#e0e0e0] dark:border-[#393939]">
        <nav className="-mb-px flex space-x-8">
          <button
            onClick={() => setActiveTab('active')}
            className={`flex items-center space-x-2 py-4 px-1 border-b-2 font-medium text-sm ${
              activeTab === 'active'
                ? 'border-[#da1e28] text-[#da1e28]'
                : 'border-transparent text-[#525252] dark:text-[#a8a8a8] hover:text-[#161616] dark:hover:text-white'
            }`}
          >
            <Bell className="h-4 w-4" />
            <span>Active Alerts</span>
            {activeAlerts.length > 0 && (
              <span className="ml-1.5 px-1.5 py-0.5 bg-[#da1e28] text-white text-xs rounded-sm font-medium">
                {activeAlerts.length}
              </span>
            )}
          </button>
          <button
            onClick={() => setActiveTab('rules')}
            className={`flex items-center space-x-2 py-4 px-1 border-b-2 font-medium text-sm ${
              activeTab === 'rules'
                ? 'border-[#da1e28] text-[#da1e28]'
                : 'border-transparent text-[#525252] dark:text-[#a8a8a8] hover:text-[#161616] dark:hover:text-white'
            }`}
          >
            <Bell className="h-4 w-4" />
            <span>Alert Rules</span>
          </button>
          <button
            onClick={() => setActiveTab('windows')}
            className={`flex items-center space-x-2 py-4 px-1 border-b-2 font-medium text-sm ${
              activeTab === 'windows'
                ? 'border-[#da1e28] text-[#da1e28]'
                : 'border-transparent text-[#525252] dark:text-[#a8a8a8] hover:text-[#161616] dark:hover:text-white'
            }`}
          >
            <Clock className="h-4 w-4" />
            <span>Maintenance Windows</span>
          </button>
        </nav>
      </div>

      {activeTab === 'rules' && (
        <>
          {/* Add Alert Form */}
          {showAddForm && (
            <div className="mb-6 bg-white dark:bg-[#262626] rounded-sm shadow-sm border border-[#e0e0e0] dark:border-[#393939] p-6">
              <h2 className="text-lg font-semibold text-[#161616] dark:text-white mb-4">Add Alert Rule</h2>
              <form onSubmit={handleSubmit} className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-[#161616] dark:text-[#a8a8a8] mb-1">Name *</label>
                    <input
                      type="text"
                      value={newAlert.name}
                      onChange={(e) => setNewAlert({ ...newAlert, name: e.target.value })}
                      className="w-full px-3 py-2 border border-[#c6c6c6] dark:border-[#525252] bg-white dark:bg-[#262626] text-[#161616] dark:text-white rounded-sm focus:ring-1 focus:ring-[#da1e28]"
                      placeholder="Device Down Alert"
                      required
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-[#161616] dark:text-[#a8a8a8] mb-1">Alert Type *</label>
                    <select
                      value={newAlert.alert_type}
                      onChange={(e) => setNewAlert({ ...newAlert, alert_type: e.target.value })}
                      className="w-full px-3 py-2 border border-[#c6c6c6] dark:border-[#525252] bg-white dark:bg-[#262626] text-[#161616] dark:text-white rounded-sm focus:ring-1 focus:ring-[#da1e28]"
                    >
                      {ALERT_TYPES.map((type) => (
                        <option key={type} value={type} className="bg-white dark:bg-[#262626]">
                          {type}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-[#161616] dark:text-[#a8a8a8] mb-1">Channel *</label>
                    <select
                      value={newAlert.channel}
                      onChange={(e) => setNewAlert({ ...newAlert, channel: e.target.value })}
                      className="w-full px-3 py-2 border border-[#c6c6c6] dark:border-[#525252] bg-white dark:bg-[#262626] text-[#161616] dark:text-white rounded-sm focus:ring-1 focus:ring-[#da1e28]"
                    >
                      {CHANNELS.map((c) => (
                        <option key={c.value} value={c.value} className="bg-white dark:bg-[#262626]">
                          {c.label}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                <div className="bg-[#f4f4f4] dark:bg-[#262626] p-4 rounded-sm">
                  <p className="text-sm text-[#525252] dark:text-[#a8a8a8]">
                    Channel configuration will be set after creation. Select a channel type first.
                  </p>
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
                    disabled={createMutation.isPending}
                    className="px-4 py-2 bg-[#161616] text-white rounded-sm hover:bg-[#525252] disabled:opacity-50"
                  >
                    {createMutation.isPending ? 'Creating...' : 'Create Alert'}
                  </button>
                </div>
              </form>
            </div>
          )}

          {/* Alerts List */}
          <div className="bg-white dark:bg-[#262626] rounded-sm shadow-sm border border-[#e0e0e0] dark:border-[#393939] overflow-hidden">
            <div className="px-6 py-4 border-b border-[#e0e0e0] dark:border-[#393939]">
              <h2 className="text-lg font-semibold text-[#161616] dark:text-white">Alert Rules</h2>
            </div>
            <div className="divide-y divide-[#e0e0e0] dark:divide-[#393939]">
              {isLoading ? (
                <div className="px-6 py-8 text-center text-[#525252] dark:text-[#a8a8a8]">Loading alerts...</div>
              ) : alerts.length === 0 ? (
                <div className="px-6 py-8 text-center text-[#525252] dark:text-[#a8a8a8]">
                  No alert rules configured. Add your first alert above.
                </div>
              ) : (
                alerts.map((alert) => (
                  <div key={alert.id} className="px-6 py-4 hover:bg-[#f4f4f4] dark:hover:bg-[#393939]">
                    <div className="flex items-center justify-between">
                      <div className="flex-1">
                        <div className="flex items-center space-x-3">
                          <span className="font-medium text-[#161616] dark:text-white">{alert.name}</span>
                          <span className="px-2 py-0.5 bg-[#e0e0e0] dark:bg-[#262626] text-[#161616] dark:text-[#f4f4f4] text-xs rounded">
                            {alert.alert_type}
                          </span>
                          <span className="px-2 py-0.5 bg-[#e0e0e0] dark:bg-[#262626] text-[#525252] dark:text-[#a8a8a8] text-xs rounded">
                            {alert.channel}
                          </span>
                          {!alert.enabled && (
                            <span className="px-2 py-0.5 bg-[#fcf4d6] text-[#b28600] text-xs rounded">
                              Disabled
                            </span>
                          )}
                        </div>
                      </div>
                      <div className="flex items-center space-x-2">
                        <button
                          onClick={() => handleTest(alert.id)}
                          className="p-2 text-[#525252] dark:text-[#a8a8a8] hover:bg-[#e0e0e0] dark:hover:bg-[#393939] rounded-sm"
                          title="Test alert"
                        >
                          <Send className="h-4 w-4" />
                        </button>
                        <button
                          onClick={() => deleteMutation.mutate(alert.id)}
                          className="p-2 text-[#da1e28] dark:text-[#ff8389] hover:bg-[#fff0f1] dark:hover:bg-[#520408] rounded-sm"
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
        </>
      )}

      {activeTab === 'active' && (
        <div className="bg-white dark:bg-[#262626] rounded-sm shadow-sm border border-[#e0e0e0] dark:border-[#393939] overflow-hidden">
          <div className="px-6 py-4 border-b border-[#e0e0e0] dark:border-[#393939] flex justify-between items-center">
            <h2 className="text-lg font-semibold text-[#161616] dark:text-white">Active Alerts</h2>
            <span className="text-sm text-[#525252] dark:text-[#a8a8a8]">Refreshes every 15s</span>
          </div>
          <div className="divide-y divide-[#e0e0e0] dark:divide-[#393939]">
            {activeAlertsLoading ? (
              <div className="px-6 py-8 text-center text-[#525252] dark:text-[#a8a8a8]">Loading alerts...</div>
            ) : activeAlerts.length === 0 ? (
              <div className="px-6 py-8 text-center text-[#525252] dark:text-[#a8a8a8]">
                No active alerts. All systems clear.
              </div>
            ) : (
              activeAlerts.map((alert) => (
                <div
                  key={alert.key}
                  className={`px-6 py-4 flex items-center justify-between ${
                    alert.status === 'firing'
                      ? 'bg-[#fff0f1] dark:bg-[#520408]'
                      : 'bg-[#fcf4d6] dark:bg-[#483501]'
                  }`}
                >
                  <div className="flex items-start space-x-3">
                    <div className="mt-0.5">
                      <span
                        className={`inline-flex px-2 py-0.5 text-xs rounded-sm font-medium ${
                          alert.severity === 'critical'
                            ? 'bg-[#da1e28] text-white'
                            : alert.severity === 'warning'
                            ? 'bg-[#f1c21b] text-[#161616]'
                            : 'bg-[#e0e0e0] text-[#161616]'
                        }`}
                      >
                        {alert.severity}
                      </span>
                    </div>
                    <div>
                      <p className="text-sm font-medium text-[#161616] dark:text-white">{alert.title}</p>
                      <p className="text-xs text-[#525252] dark:text-[#a8a8a8]">{alert.message}</p>
                      <p className="text-xs text-[#a8a8a8] dark:text-[#525252] mt-0.5">
                        {alert.status === 'acknowledged' && (
                          <span className="text-[#b28600] font-medium">Acknowledged · </span>
                        )}
                        Fired {new Date(alert.fired_at * 1000).toLocaleTimeString()}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center space-x-1">
                    {alert.status === 'firing' && (
                      <button
                        onClick={() => acknowledge(alert.key)}
                        className="p-1.5 text-[#525252] dark:text-[#a8a8a8] hover:bg-[#e0e0e0] dark:hover:bg-[#393939] rounded-sm"
                        title="Acknowledge"
                      >
                        <Check className="h-4 w-4" />
                      </button>
                    )}
                    <button
                      onClick={() => resolve(alert.key)}
                      className="p-1.5 text-[#da1e28] dark:text-[#ff8389] hover:bg-[#fff0f1] dark:hover:bg-[#520408] rounded-sm"
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

      {activeTab === 'windows' && (
        <>
          {/* Add Maintenance Window Form */}
          {showWindowForm && (
            <div className="mb-6 bg-white dark:bg-[#262626] rounded-sm shadow-sm border border-[#e0e0e0] dark:border-[#393939] p-6">
              <h2 className="text-lg font-semibold text-[#161616] dark:text-white mb-4">Add Maintenance Window</h2>
              <form onSubmit={handleWindowSubmit} className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="md:col-span-2">
                    <label className="block text-sm font-medium text-[#161616] dark:text-[#a8a8a8] mb-1">Name *</label>
                    <input
                      type="text"
                      value={newWindow.name}
                      onChange={(e) => setNewWindow({ ...newWindow, name: e.target.value })}
                      className="w-full px-3 py-2 border border-[#c6c6c6] dark:border-[#525252] bg-white dark:bg-[#262626] text-[#161616] dark:text-white rounded-sm focus:ring-1 focus:ring-[#da1e28]"
                      placeholder="Scheduled Maintenance"
                      required
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-[#161616] dark:text-[#a8a8a8] mb-1">Start Time *</label>
                    <input
                      type="datetime-local"
                      value={newWindow.start_time}
                      onChange={(e) => setNewWindow({ ...newWindow, start_time: e.target.value })}
                      className="w-full px-3 py-2 border border-[#c6c6c6] dark:border-[#525252] bg-white dark:bg-[#262626] text-[#161616] dark:text-white rounded-sm focus:ring-1 focus:ring-[#da1e28]"
                      required
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-[#161616] dark:text-[#a8a8a8] mb-1">End Time *</label>
                    <input
                      type="datetime-local"
                      value={newWindow.end_time}
                      onChange={(e) => setNewWindow({ ...newWindow, end_time: e.target.value })}
                      className="w-full px-3 py-2 border border-[#c6c6c6] dark:border-[#525252] bg-white dark:bg-[#262626] text-[#161616] dark:text-white rounded-sm focus:ring-1 focus:ring-[#da1e28]"
                      required
                    />
                  </div>
                  <div className="md:col-span-2">
                    <label className="block text-sm font-medium text-[#161616] dark:text-[#a8a8a8] mb-1">Description</label>
                    <textarea
                      value={newWindow.description}
                      onChange={(e) => setNewWindow({ ...newWindow, description: e.target.value })}
                      className="w-full px-3 py-2 border border-[#c6c6c6] dark:border-[#525252] bg-white dark:bg-[#262626] text-[#161616] dark:text-white rounded-sm focus:ring-1 focus:ring-[#da1e28]"
                      rows={3}
                      placeholder="Planned network maintenance window"
                    />
                  </div>
                </div>
                <div className="flex justify-end space-x-2">
                  <button
                    type="button"
                    onClick={() => setShowWindowForm(false)}
                    className="px-4 py-2 text-[#161616] dark:text-[#a8a8a8] bg-[#e0e0e0] dark:bg-[#262626] rounded-sm hover:bg-[#e0e0e0] dark:hover:bg-[#393939]"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={createWindowMutation.isPending}
                    className="px-4 py-2 bg-[#161616] text-white rounded-sm hover:bg-[#525252] disabled:opacity-50"
                  >
                    {createWindowMutation.isPending ? 'Creating...' : 'Create Window'}
                  </button>
                </div>
              </form>
            </div>
          )}

          {/* Maintenance Windows List */}
          <div className="bg-white dark:bg-[#262626] rounded-sm shadow-sm border border-[#e0e0e0] dark:border-[#393939] overflow-hidden">
            <div className="px-6 py-4 border-b border-[#e0e0e0] dark:border-[#393939]">
              <h2 className="text-lg font-semibold text-[#161616] dark:text-white">Maintenance Windows</h2>
            </div>
            <div className="divide-y divide-[#e0e0e0] dark:divide-[#393939]">
              {windowsLoading ? (
                <div className="px-6 py-8 text-center text-[#525252] dark:text-[#a8a8a8]">Loading windows...</div>
              ) : windows.length === 0 ? (
                <div className="px-6 py-8 text-center text-[#525252] dark:text-[#a8a8a8]">
                  No maintenance windows configured. Add a window to suppress alerts during planned downtime.
                </div>
              ) : (
                windows.map((window) => {
                  const active = isWindowActive(window.start_time, window.end_time);
                  return (
                    <div key={window.id} className="px-6 py-4 hover:bg-[#f4f4f4] dark:hover:bg-[#393939]">
                      <div className="flex items-center justify-between">
                        <div className="flex-1">
                          <div className="flex items-center space-x-3">
                            <span className="font-medium text-[#161616] dark:text-white">{window.name}</span>
                            {active && (
                              <span className="px-2 py-0.5 bg-[#defbe6] text-[#24a148] text-xs rounded font-medium">
                                Active
                              </span>
                            )}
                          </div>
                          <p className="text-sm text-[#525252] dark:text-[#a8a8a8] mt-1">
                            {new Date(window.start_time).toLocaleString()} — {new Date(window.end_time).toLocaleString()}
                          </p>
                          {window.description && (
                            <p className="text-xs text-[#a8a8a8] dark:text-[#525252] mt-1">{window.description}</p>
                          )}
                        </div>
                        <button
                          onClick={() => deleteWindowMutation.mutate(window.id)}
                          className="p-2 text-[#da1e28] dark:text-[#ff8389] hover:bg-[#fff0f1] dark:hover:bg-[#520408] rounded-sm"
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
