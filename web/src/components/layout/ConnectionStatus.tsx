import { useState, useEffect } from 'react';
import { Wifi, WifiOff } from 'lucide-react';
import { apiClient } from '../../api';

export function ConnectionStatus() {
  const [isOnline, setIsOnline] = useState(true);
  const [isChecking, setIsChecking] = useState(false);

  useEffect(() => {
    const checkConnection = async () => {
      setIsChecking(true);
      try {
        await apiClient.get('/health', { timeout: 3000 });
        setIsOnline(true);
      } catch {
        setIsOnline(false);
      } finally {
        setIsChecking(false);
      }
    };

    checkConnection();
    const interval = setInterval(checkConnection, 10000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div
      className={`flex items-center space-x-2 px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${
        isOnline
          ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
          : 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'
      }`}
      title={isOnline ? 'Backend connected' : 'Backend disconnected'}
    >
      {isChecking ? (
        <div className="animate-spin rounded-full h-3 w-3 border-2 border-current border-t-transparent" />
      ) : isOnline ? (
        <Wifi className="h-3.5 w-3.5" />
      ) : (
        <WifiOff className="h-3.5 w-3.5" />
      )}
      <span className="hidden sm:inline">{isOnline ? 'Connected' : 'Disconnected'}</span>
    </div>
  );
}
