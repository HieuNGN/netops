import { Link, useLocation, useNavigate } from 'react-router-dom';
import { Network, Activity, Server, AlertTriangle, Settings, History, LogOut } from 'lucide-react';
import { useTheme } from '../../hooks/useTheme';
import { useAuth } from '../../hooks/useAuth';
import { ConnectionStatus } from './ConnectionStatus';

const navItems = [
  { path: '/', icon: Activity, label: 'Dashboard' },
  { path: '/topology', icon: Network, label: 'Topology' },
  { path: '/topology/history', icon: History, label: 'History' },
  { path: '/devices', icon: Server, label: 'Devices' },
  { path: '/checks', icon: Activity, label: 'Service Checks' },
  { path: '/alerts', icon: AlertTriangle, label: 'Alerts' },
  { path: '/settings', icon: Settings, label: 'Settings' },
];

export function Header() {
  const location = useLocation();
  const { isDark, toggleTheme } = useTheme();
  const { username, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => { logout(); navigate('/login'); };

  return (
    <header className="bg-background border-b border-border">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between items-center h-16">
          <div className="flex items-center">
            <Link to="/" className="flex items-center space-x-2">
              <Network className="h-8 w-8 text-thinkpad-red" />
              <span className="text-xl font-bold text-foreground">NetOps</span>
            </Link>
          </div>

          <nav className="flex items-center space-x-1 overflow-x-auto">
            {navItems.map((item) => {
              const isActive = location.pathname === item.path;
              return (
                <Link
                  key={item.path}
                  to={item.path}
                  className={`flex items-center space-x-2 px-3 py-2 rounded-sm text-sm font-medium transition-colors ${
                    isActive
                      ? 'bg-ibm-blue text-white'
                      : 'text-muted-foreground hover:bg-surface-hover'
                  }`}
                >
                  <item.icon className="h-4 w-4" />
                  <span className="hidden sm:inline">{item.label}</span>
                </Link>
              );
            })}

            <div className="flex items-center space-x-3 ml-2">
              <ConnectionStatus />

              {username && (
                <button onClick={handleLogout} className="flex items-center gap-1 px-2 py-1.5 text-xs text-muted-foreground hover:bg-surface-hover rounded-sm" title="Logout">
                  <LogOut className="h-3.5 w-3.5" />
                  <span className="hidden sm:inline">{username}</span>
                </button>
              )}

              {/* Theme Toggle TrackPoint */}
              <button
                onClick={toggleTheme}
                className="group relative flex items-center justify-center focus:outline-none"
                title={isDark ? 'Dark mode (click to switch to light)' : 'Light mode (click to switch to dark)'}
              >
                <span className="sr-only">Toggle theme</span>
                {/* TrackPoint nub */}
                <span
                  className={`
                    relative inline-flex items-center justify-center
                    w-5 h-5 rounded-full
                    transition-all duration-200 ease-out
                    ${isDark
                      ? 'bg-thinkpad-red shadow-[0_1px_3px_var(--canvas-shadow)]'
                      : 'bg-surface-pressed shadow-[inset_0_1px_2px_rgba(0,0,0,0.15)]'
                    }
                    group-hover:scale-110 group-active:scale-95
                  `}
                >
                  {/* TrackPoint texture dots */}
                  <span className={`
                    absolute inset-0 rounded-full
                    ${isDark
                      ? 'bg-[radial-gradient(circle_at_30%_30%,rgba(255,255,255,0.15)_1px,transparent_1px)] bg-[length:3px_3px]'
                      : 'bg-[radial-gradient(circle_at_30%_30%,rgba(0,0,0,0.08)_1px,transparent_1px)] bg-[length:3px_3px]'
                    }
                  `} />
                  {/* Small specular highlight */}
                  <span className={`
                    absolute top-[2px] left-[3px] w-[6px] h-[3px] rounded-[50%]
                    ${isDark ? 'bg-white/20' : 'bg-white/60'}
                  `} />
                </span>
              </button>
            </div>
          </nav>
        </div>
      </div>
    </header>
  );
}