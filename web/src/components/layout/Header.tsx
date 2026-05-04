import { Link, useLocation } from 'react-router-dom';
import { Network, Activity, Server, AlertTriangle, Settings, Sun, Moon } from 'lucide-react';
import { useTheme } from '../../hooks/useTheme';
import { ConnectionStatus } from './ConnectionStatus';

const navItems = [
  { path: '/', icon: Activity, label: 'Dashboard' },
  { path: '/topology', icon: Network, label: 'Topology' },
  { path: '/devices', icon: Server, label: 'Devices' },
  { path: '/checks', icon: Activity, label: 'Service Checks' },
  { path: '/alerts', icon: AlertTriangle, label: 'Alerts' },
  { path: '/settings', icon: Settings, label: 'Settings' },
];

export function Header() {
  const location = useLocation();
  const { isDark, toggleTheme } = useTheme();

  return (
    <header className="bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-700 shadow-sm">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between items-center h-16">
          <div className="flex items-center">
            <Link to="/" className="flex items-center space-x-2">
              <Network className="h-8 w-8 text-purple-600" />
              <span className="text-xl font-bold text-gray-900 dark:text-white">NetOps</span>
            </Link>
          </div>

          <nav className="flex items-center space-x-1">
            {navItems.map((item) => {
              const isActive = location.pathname === item.path;
              return (
                <Link
                  key={item.path}
                  to={item.path}
                  className={`flex items-center space-x-2 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                    isActive
                      ? 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300'
                      : 'text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800'
                  }`}
                >
                  <item.icon className="h-4 w-4" />
                  <span className="hidden sm:inline">{item.label}</span>
                </Link>
              );
            })}

            <div className="flex items-center space-x-3 ml-2">
              <ConnectionStatus />

              {/* Theme Toggle Switch */}
              <div className="flex items-center space-x-2">
                <Sun className="h-4 w-4 text-amber-500" />
                <button
                  onClick={toggleTheme}
                  className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-purple-500 focus:ring-offset-2 ${
                    isDark ? 'bg-purple-600' : 'bg-gray-300'
                  }`}
                  title={isDark ? 'Dark mode (click to switch to light)' : 'Light mode (click to switch to dark)'}
                >
                  <span className="sr-only">Toggle theme</span>
                  <span
                    className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                      isDark ? 'translate-x-6' : 'translate-x-1'
                    }`}
                  />
                </button>
                <Moon className="h-4 w-4 text-purple-400" />
              </div>
            </div>
          </nav>
        </div>
      </div>
    </header>
  );
}
