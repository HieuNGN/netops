import { useState, useEffect, useRef } from 'react';
import { Wifi, WifiOff } from 'lucide-react';
import { apiClient } from '../../api';

export function ConnectionStatus() {
  const [isOnline, setIsOnline] = useState(true);
  const [isChecking, setIsChecking] = useState(false);
  const [lastCheck, setLastCheck] = useState<Date | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  const checkConnection = async () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }

    abortControllerRef.current = new AbortController();
    setIsChecking(true);

    try {
      await apiClient.get('/api/health', {
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
      className={`flex items-center space-x-2 px-3 py-1.5 rounded-sm text-xs font-medium transition-colors ${
        isOnline
          ? 'bg-badge-success-bg text-badge-success-fg'
          : 'bg-badge-destructive-bg text-badge-destructive-fg'
      }`}
      title={isOnline ? `Backend connected${lastCheck ? ` • Last check: ${lastCheck.toLocaleTimeString()}` : ''}` : 'Backend disconnected - retrying...'}
    >
      {isChecking ? (
        <div className="animate-spin rounded-sm h-3 w-3 border-2 border-current border-t-transparent" />
      ) : isOnline ? (
        <Wifi className="h-3.5 w-3.5" />
      ) : (
        <WifiOff className="h-3.5 w-3.5" />
      )}
      <span className="hidden sm:inline">{isOnline ? 'Connected' : 'Disconnected'}</span>
    </div>
  );
}