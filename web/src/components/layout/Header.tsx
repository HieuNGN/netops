import { Link, useLocation, useNavigate } from 'react-router-dom';
import { Network, Activity, Server, AlertTriangle, Settings, History, LogOut } from 'lucide-react';
import { useTheme } from '../../hooks/useTheme';
import { useAuth } from '../../hooks/useAuth';
import { ConnectionStatus } from './ConnectionStatus';
import { useEnvironmentProfiles } from '../../hooks/useConfig';

const navItems = [
  { path: '/', icon: Activity, label: 'Dashboard' },
  { path: '/topology', icon: Network, label: 'Topology' },
  { path: '/topology/history', icon: History, label: 'History' },
  { path: '/devices', icon: Server, label: 'Devices' },
  { path: '/checks', icon: Activity, label: 'Checks' },
  { path: '/alerts', icon: AlertTriangle, label: 'Alerts' },
  { path: '/settings', icon: Settings, label: 'Settings' },
];

const PROFILE_ACCENT: Record<string, string> = {
  homelab: 'bg-cisco-green',
  small_business: 'bg-ibm-cyan',
  datacenter: 'bg-ibm-purple',
};

export function Header() {
  const location = useLocation();
  const { isDark, toggleTheme } = useTheme();
  const { username, logout } = useAuth();
  const navigate = useNavigate();
  const { activeProfile, isGuessed } = useEnvironmentProfiles();

  const handleLogout = () => { logout(); navigate('/login'); };

  const accentClass = PROFILE_ACCENT[activeProfile] || 'bg-muted-foreground';

  return (
    <header className="bg-card border-b border-border">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between items-center h-14">
          <div className="flex items-center gap-3">
            <Link to="/" className="flex items-center space-x-2">
              <Network className="h-6 w-6 text-thinkpad-red" />
              <span className="text-xs font-semibold text-foreground">NetOps</span>
            </Link>
            <div
              className="hidden md:inline-flex items-center gap-1.5 px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide rounded-sm bg-surface-subtle text-muted-foreground"
              title={isGuessed ? 'Auto-detected profile — confirm in Settings' : 'Active environment profile'}
            >
              <span className={`inline-block h-1.5 w-1.5 rounded-full ${accentClass}`} />
              {activeProfile}
              {isGuessed && <span className="text-ibm-yellow">·</span>}
            </div>
          </div>

          <nav className="flex items-center space-x-0.5 overflow-x-auto">
            {navItems.map((item) => {
              const isActive = location.pathname === item.path;
              return (
                <Link
                  key={item.path}
                  to={item.path}
                  className={`flex items-center space-x-1.5 px-2.5 py-1.5 rounded-sm text-xs font-medium transition-colors ${
                    isActive
                      ? 'bg-ibm-blue/10 text-ibm-blue'
                      : 'text-muted-foreground hover:bg-surface-hover hover:text-foreground'
                  }`}
                >
                  <item.icon className="h-3.5 w-3.5" />
                  <span className="hidden sm:inline">{item.label}</span>
                </Link>
              );
            })}

            <div className="flex items-center space-x-2 ml-2 pl-2 border-l border-border">
              <ConnectionStatus />

              {username && (
                <button
                  onClick={handleLogout}
                  className="inline-flex items-center gap-1 px-2 py-1 text-xs text-muted-foreground hover:bg-surface-hover rounded-sm"
                  title={`Logged in as ${username} — click to logout`}
                >
                  <LogOut className="h-3.5 w-3.5" />
                  <span className="hidden sm:inline">{username}</span>
                </button>
              )}

              {/* Theme Toggle TrackPoint */}
              <button
                onClick={toggleTheme}
                className="group relative flex items-center justify-center focus:outline-none"
                title={isDark ? 'Dark mode (click to switch to light)' : 'Light mode (click to switch to dark)'}
                aria-label="Toggle theme"
              >
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
                  <span className={`
                    absolute inset-0 rounded-full
                    ${isDark
                      ? 'bg-[radial-gradient(circle_at_30%_30%,rgba(255,255,255,0.15)_1px,transparent_1px)] bg-[length:3px_3px]'
                      : 'bg-[radial-gradient(circle_at_30%_30%,rgba(0,0,0,0.08)_1px,transparent_1px)] bg-[length:3px_3px]'
                    }
                  `} />
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