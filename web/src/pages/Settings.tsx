import { useState, useEffect } from 'react';
import { useTheme } from '../hooks/useTheme';
import { Sun, Moon, Monitor, Save, Check } from 'lucide-react';
import { useToast } from '../components/ui';

export function Settings() {
  const { theme, setTheme } = useTheme();
  const toast = useToast();
  const [isSaving, setIsSaving] = useState(false);
  const [localTheme, setLocalTheme] = useState<'light' | 'dark' | 'system'>(theme);

  // Sync local state with theme hook
  useEffect(() => {
    setLocalTheme(theme);
  }, [theme]);

  const handleThemeChange = (newTheme: 'light' | 'dark' | 'system') => {
    setLocalTheme(newTheme);
    setTheme(newTheme);
  };

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
        <h1 className="text-2xl font-bold text-[#161616] dark:text-white">Settings</h1>
        <p className="text-[#525252] dark:text-[#a8a8a8] mt-1">Application configuration</p>
      </div>

      <div className="space-y-6">
        {/* Theme Settings */}
        <div className="bg-white dark:bg-[#262626] rounded-sm shadow-sm border border-[#e0e0e0] dark:border-[#393939] p-6">
          <h2 className="text-lg font-semibold text-[#161616] dark:text-white mb-4">Appearance</h2>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-[#161616] dark:text-[#a8a8a8] mb-1">
                Theme Mode
              </label>
              <div className="grid grid-cols-3 gap-3">
                {(['light', 'dark', 'system'] as const).map((t) => (
                  <button
                    key={t}
                    onClick={() => handleThemeChange(t)}
                    className={`flex items-center justify-center space-x-2 px-4 py-3 rounded-sm border transition-all ${
                      localTheme === t
                        ? 'border-[#da1e28] bg-[#f4f4f4] dark:bg-[#262626] text-[#161616] dark:text-[#f4f4f4]'
                        : 'border-[#e0e0e0] dark:border-[#525252] text-[#161616] dark:text-[#a8a8a8] hover:bg-[#f4f4f4] dark:hover:bg-[#393939]'
                    }`}
                  >
                    {t === 'light' && <Sun className="h-4 w-4" />}
                    {t === 'dark' && <Moon className="h-4 w-4" />}
                    {t === 'system' && <Monitor className="h-4 w-4" />}
                    <span className="capitalize">{t}</span>
                  </button>
                ))}
              </div>
              <p className="text-sm text-[#525252] dark:text-[#a8a8a8] mt-2">
                Current: <span className="font-medium capitalize">{localTheme}</span>
                {localTheme === 'system' && ' (follows system preference)'}
              </p>
            </div>

            {/* Quick Toggle */}
            <div className="flex items-center justify-between pt-4 border-t border-[#e0e0e0] dark:border-[#393939]">
              <div className="flex items-center space-x-2">
                <Sun className="h-5 w-5 text-amber-500" />
                <Moon className="h-5 w-5 text-[#a8a8a8]" />
              </div>
              <div className="flex items-center space-x-2">
                <span className="text-sm text-[#525252] dark:text-[#a8a8a8]">
                  {localTheme === 'dark' ? 'Dark' : localTheme === 'light' ? 'Light' : 'System'} mode active
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* SNMP Settings */}
        <div className="bg-white dark:bg-[#262626] rounded-sm shadow-sm border border-[#e0e0e0] dark:border-[#393939] p-6">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-lg font-semibold text-[#161616] dark:text-white">SNMP Configuration</h2>
            <button
              onClick={handleSaveSnmp}
              disabled={isSaving}
              className="flex items-center space-x-2 px-4 py-2 bg-[#161616] text-white rounded-sm hover:bg-[#525252] disabled:opacity-50"
            >
              {isSaving ? <Check className="h-4 w-4" /> : <Save className="h-4 w-4" />}
              <span>{isSaving ? 'Saving...' : 'Save'}</span>
            </button>
          </div>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-[#161616] dark:text-[#a8a8a8] mb-1">
                Default Community
              </label>
              <input
                type="text"
                value={snmpConfig.community}
                onChange={(e) => setSnmpConfig({ ...snmpConfig, community: e.target.value })}
                className="w-full px-3 py-2 border border-[#c6c6c6] dark:border-[#525252] bg-white dark:bg-[#262626] text-[#161616] dark:text-white rounded-sm focus:ring-1 focus:ring-[#da1e28]"
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-[#161616] dark:text-[#a8a8a8] mb-1">
                  Timeout (seconds)
                </label>
                <input
                  type="number"
                  value={snmpConfig.timeout}
                  onChange={(e) => setSnmpConfig({ ...snmpConfig, timeout: parseInt(e.target.value) || 5 })}
                  min="1"
                  max="30"
                  className="w-full px-3 py-2 border border-[#c6c6c6] dark:border-[#525252] bg-white dark:bg-[#262626] text-[#161616] dark:text-white rounded-sm focus:ring-1 focus:ring-[#da1e28]"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-[#161616] dark:text-[#a8a8a8] mb-1">
                  Retries
                </label>
                <input
                  type="number"
                  value={snmpConfig.retries}
                  onChange={(e) => setSnmpConfig({ ...snmpConfig, retries: parseInt(e.target.value) || 3 })}
                  min="0"
                  max="10"
                  className="w-full px-3 py-2 border border-[#c6c6c6] dark:border-[#525252] bg-white dark:bg-[#262626] text-[#161616] dark:text-white rounded-sm focus:ring-1 focus:ring-[#da1e28]"
                />
              </div>
            </div>
          </div>
        </div>

        {/* Polling Settings */}
        <div className="bg-white dark:bg-[#262626] rounded-sm shadow-sm border border-[#e0e0e0] dark:border-[#393939] p-6">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-lg font-semibold text-[#161616] dark:text-white">Polling Settings</h2>
            <button
              onClick={handleSavePolling}
              disabled={isSaving}
              className="flex items-center space-x-2 px-4 py-2 bg-[#161616] text-white rounded-sm hover:bg-[#525252] disabled:opacity-50"
            >
              {isSaving ? <Check className="h-4 w-4" /> : <Save className="h-4 w-4" />}
              <span>{isSaving ? 'Saving...' : 'Save'}</span>
            </button>
          </div>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-[#161616] dark:text-[#a8a8a8] mb-1">
                Topology Polling Interval (seconds)
              </label>
              <input
                type="number"
                value={pollingConfig.topology_interval}
                onChange={(e) => setPollingConfig({ ...pollingConfig, topology_interval: parseInt(e.target.value) || 30 })}
                min="5"
                max="300"
                className="w-full px-3 py-2 border border-[#c6c6c6] dark:border-[#525252] bg-white dark:bg-[#262626] text-[#161616] dark:text-white rounded-sm focus:ring-1 focus:ring-[#da1e28]"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-[#161616] dark:text-[#a8a8a8] mb-1">
                Service Check Default Interval (seconds)
              </label>
              <input
                type="number"
                value={pollingConfig.check_interval}
                onChange={(e) => setPollingConfig({ ...pollingConfig, check_interval: parseInt(e.target.value) || 60 })}
                min="10"
                max="3600"
                className="w-full px-3 py-2 border border-[#c6c6c6] dark:border-[#525252] bg-white dark:bg-[#262626] text-[#161616] dark:text-white rounded-sm focus:ring-1 focus:ring-[#da1e28]"
              />
            </div>
          </div>
        </div>

        {/* Connection Settings */}
        <div className="bg-white dark:bg-[#262626] rounded-sm shadow-sm border border-[#e0e0e0] dark:border-[#393939] p-6">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-lg font-semibold text-[#161616] dark:text-white">API Connection</h2>
            <button
              onClick={handleSaveApiUrl}
              className="flex items-center space-x-2 px-4 py-2 bg-[#161616] text-white rounded-sm hover:bg-[#525252]"
            >
              <Save className="h-4 w-4" />
              <span>Save</span>
            </button>
          </div>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-[#161616] dark:text-[#a8a8a8] mb-1">
                Backend API URL
              </label>
              <input
                type="text"
                value={apiUrl}
                onChange={(e) => setApiUrl(e.target.value)}
                className="w-full px-3 py-2 border border-[#c6c6c6] dark:border-[#525252] bg-white dark:bg-[#262626] text-[#161616] dark:text-white rounded-sm focus:ring-1 focus:ring-[#da1e28]"
              />
              <p className="text-sm text-[#525252] dark:text-[#a8a8a8] mt-1">
                Changes require a page reload to take effect
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default Settings;
