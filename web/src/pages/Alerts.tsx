import { useState } from 'react';
import { Plus, Trash2, Send } from 'lucide-react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { alertsApi } from '../api';
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

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Alerts</h1>
          <p className="text-gray-600 dark:text-gray-400 mt-1">Configure alert rules and notifications</p>
        </div>
        <button
          onClick={() => setShowAddForm(true)}
          className="flex items-center space-x-2 px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700"
        >
          <Plus className="h-4 w-4" />
          <span>Add Alert</span>
        </button>
      </div>

      {/* Add Alert Form */}
      {showAddForm && (
        <div className="mb-6 bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Add Alert Rule</h2>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Name *</label>
                <input
                  type="text"
                  value={newAlert.name}
                  onChange={(e) => setNewAlert({ ...newAlert, name: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white rounded-lg focus:ring-2 focus:ring-purple-500"
                  placeholder="Device Down Alert"
                  required
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Alert Type *</label>
                <select
                  value={newAlert.alert_type}
                  onChange={(e) => setNewAlert({ ...newAlert, alert_type: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white rounded-lg focus:ring-2 focus:ring-purple-500"
                >
                  {ALERT_TYPES.map((type) => (
                    <option key={type} value={type} className="bg-white dark:bg-gray-700">
                      {type}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Channel *</label>
                <select
                  value={newAlert.channel}
                  onChange={(e) => setNewAlert({ ...newAlert, channel: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white rounded-lg focus:ring-2 focus:ring-purple-500"
                >
                  {CHANNELS.map((c) => (
                    <option key={c.value} value={c.value} className="bg-white dark:bg-gray-700">
                      {c.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {/* Channel-specific config fields would go here */}
            <div className="bg-gray-50 dark:bg-gray-700 p-4 rounded-lg">
              <p className="text-sm text-gray-600 dark:text-gray-400">
                Channel configuration will be set after creation. Select a channel type first.
              </p>
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
                disabled={createMutation.isPending}
                className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50"
              >
                {createMutation.isPending ? 'Creating...' : 'Create Alert'}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Alerts List */}
      <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-700">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Alert Rules</h2>
        </div>
        <div className="divide-y divide-gray-200 dark:divide-gray-700">
          {isLoading ? (
            <div className="px-6 py-8 text-center text-gray-500 dark:text-gray-400">Loading alerts...</div>
          ) : alerts.length === 0 ? (
            <div className="px-6 py-8 text-center text-gray-500 dark:text-gray-400">
              No alert rules configured. Add your first alert above.
            </div>
          ) : (
            alerts.map((alert) => (
              <div key={alert.id} className="px-6 py-4 hover:bg-gray-50 dark:hover:bg-gray-700">
                <div className="flex items-center justify-between">
                  <div className="flex-1">
                    <div className="flex items-center space-x-3">
                      <span className="font-medium text-gray-900 dark:text-white">{alert.name}</span>
                      <span className="px-2 py-0.5 bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300 text-xs rounded">
                        {alert.alert_type}
                      </span>
                      <span className="px-2 py-0.5 bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 text-xs rounded">
                        {alert.channel}
                      </span>
                      {!alert.enabled && (
                        <span className="px-2 py-0.5 bg-yellow-100 text-yellow-700 text-xs rounded">
                          Disabled
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center space-x-2">
                    <button
                      onClick={() => handleTest(alert.id)}
                      className="p-2 text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-600 rounded-lg"
                      title="Test alert"
                    >
                      <Send className="h-4 w-4" />
                    </button>
                    <button
                      onClick={() => deleteMutation.mutate(alert.id)}
                      className="p-2 text-red-600 dark:text-red-400 hover:bg-red-100 dark:hover:bg-red-900/20 rounded-lg"
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
    </div>
  );
}
