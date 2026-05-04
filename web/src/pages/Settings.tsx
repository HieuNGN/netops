import { useState } from 'react';
import { useTheme } from '../hooks/useTheme';
import { Sun, Moon, Monitor, Save, Check } from 'lucide-react';
import { useToast } from '../components/ui';

export function Settings() {
  const { theme, setTheme } = useTheme();
  const toast = useToast();
  const [isSaving, setIsSaving] = useState(false);
  const [snmpConfig, setSnmpConfig] = useState({
    community: 'public',
    timeout: 5,
    retries: 3,
  });
  const [pollingConfig, setPollingConfig] = useState({
    topology_interval: 30,
    check_interval: 60,
  });
  const [apiUrl, setApiUrl] = useState(import.meta.env.VITE_API_URL || 'http://localhost:8000');

  const handleSaveSnmp = async () => {
    setIsSaving(true);
    try {
      localStorage.setItem('snmp_config', JSON.stringify(snmpConfig));
      toast.success('SNMP settings saved', 'Configuration updated');
    } catch (error) {
      toast.error('Failed to save SNMP settings', 'Error');
    } finally {
      setIsSaving(false);
    }
  };

  const handleSavePolling = async () => {
    setIsSaving(true);
    try {
      localStorage.setItem('polling_config', JSON.stringify(pollingConfig));
      toast.success('Polling settings saved', 'Configuration updated');
    } catch (error) {
      toast.error('Failed to save polling settings', 'Error');
    } finally {
      setIsSaving(false);
    }
  };

  const handleSaveApiUrl = () => {
    localStorage.setItem('api_url', apiUrl);
    toast.success('API URL saved', 'Page reload required');
  };

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Settings</h1>
        <p className="text-gray-600 dark:text-gray-400 mt-1">Application configuration</p>
      </div>

      <div className="space-y-6">
        {/* Theme Settings */}
        <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Appearance</h2>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Theme
              </label>
              <div className="grid grid-cols-3 gap-3">
                {(['light', 'dark', 'system'] as const).map((t) => (
                  <button
                    key={t}
                    onClick={() => setTheme(t)}
                    className={`flex items-center justify-center space-x-2 px-4 py-3 rounded-lg border transition-all ${
                      theme === t
                        ? 'border-purple-500 bg-purple-50 dark:bg-purple-900/20 text-purple-700 dark:text-purple-300'
                        : 'border-gray-200 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700'
                    }`}
                  >
                    {t === 'light' && <Sun className="h-4 w-4" />}
                    {t === 'dark' && <Moon className="h-4 w-4" />}
                    {t === 'system' && <Monitor className="h-4 w-4" />}
                    <span className="capitalize">{t}</span>
                  </button>
                ))}
              </div>
              <p className="text-sm text-gray-500 dark:text-gray-400 mt-2">
                Current: <span className="font-medium capitalize">{theme}</span>
                {theme === 'system' && ' (follows system preference)'}
              </p>
            </div>
          </div>
        </div>

        {/* SNMP Settings */}
        <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">SNMP Configuration</h2>
            <button
              onClick={handleSaveSnmp}
              disabled={isSaving}
              className="flex items-center space-x-2 px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50"
            >
              {isSaving ? <Check className="h-4 w-4" /> : <Save className="h-4 w-4" />}
              <span>{isSaving ? 'Saving...' : 'Save'}</span>
            </button>
          </div>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Default Community
              </label>
              <input
                type="text"
                value={snmpConfig.community}
                onChange={(e) => setSnmpConfig({ ...snmpConfig, community: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white rounded-lg focus:ring-2 focus:ring-purple-500"
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Timeout (seconds)
                </label>
                <input
                  type="number"
                  value={snmpConfig.timeout}
                  onChange={(e) => setSnmpConfig({ ...snmpConfig, timeout: parseInt(e.target.value) || 5 })}
                  min="1"
                  max="30"
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white rounded-lg focus:ring-2 focus:ring-purple-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Retries
                </label>
                <input
                  type="number"
                  value={snmpConfig.retries}
                  onChange={(e) => setSnmpConfig({ ...snmpConfig, retries: parseInt(e.target.value) || 3 })}
                  min="0"
                  max="10"
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white rounded-lg focus:ring-2 focus:ring-purple-500"
                />
              </div>
            </div>
          </div>
        </div>

        {/* Polling Settings */}
        <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Polling Settings</h2>
            <button
              onClick={handleSavePolling}
              disabled={isSaving}
              className="flex items-center space-x-2 px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50"
            >
              {isSaving ? <Check className="h-4 w-4" /> : <Save className="h-4 w-4" />}
              <span>{isSaving ? 'Saving...' : 'Save'}</span>
            </button>
          </div>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Topology Polling Interval (seconds)
              </label>
              <input
                type="number"
                value={pollingConfig.topology_interval}
                onChange={(e) => setPollingConfig({ ...pollingConfig, topology_interval: parseInt(e.target.value) || 30 })}
                min="5"
                max="300"
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white rounded-lg focus:ring-2 focus:ring-purple-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Service Check Default Interval (seconds)
              </label>
              <input
                type="number"
                value={pollingConfig.check_interval}
                onChange={(e) => setPollingConfig({ ...pollingConfig, check_interval: parseInt(e.target.value) || 60 })}
                min="10"
                max="3600"
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white rounded-lg focus:ring-2 focus:ring-purple-500"
              />
            </div>
          </div>
        </div>

        {/* Connection Settings */}
        <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">API Connection</h2>
            <button
              onClick={handleSaveApiUrl}
              className="flex items-center space-x-2 px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700"
            >
              <Save className="h-4 w-4" />
              <span>Save</span>
            </button>
          </div>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Backend API URL
              </label>
              <input
                type="text"
                value={apiUrl}
                onChange={(e) => setApiUrl(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white rounded-lg focus:ring-2 focus:ring-purple-500"
              />
              <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                Changes require a page reload to take effect
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
