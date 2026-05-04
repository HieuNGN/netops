import { useState, useEffect, useRef } from 'react';
import { Wifi, WifiOff } from 'lucide-react';
import { apiClient } from '../../api';

export function ConnectionStatus() {
  const [isOnline, setIsOnline] = useState(true);
  const [isChecking, setIsChecking] = useState(false);
  const [lastCheck, setLastCheck] = useState<Date | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  const checkConnection = async () => {
    // Cancel previous request if still running
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }

    abortControllerRef.current = new AbortController();
    setIsChecking(true);

    try {
      await apiClient.get('/health', {
        timeout: 3000,
        signal: abortControllerRef.current.signal
      });
      setIsOnline(true);
      setLastCheck(new Date());
    } catch {
      setIsOnline(false);
    } finally {
      setIsChecking(false);
    }
  };

  useEffect(() => {
    checkConnection();
    const interval = setInterval(checkConnection, 5000);
    return () => {
      clearInterval(interval);
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, []);

  return (
    <div
      className={`flex items-center space-x-2 px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${
        isOnline
          ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
          : 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'
      }`}
      title={isOnline ? `Backend connected${lastCheck ? ` • Last check: ${lastCheck.toLocaleTimeString()}` : ''}` : 'Backend disconnected - retrying...'}
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
