import { useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { devicesApi } from '../api';

/**
 * Subscribe to the backend /events/stream SSE feed and invalidate
 * devices/topology queries whenever the server announces a refresh.
 * Use once near the root of any page that renders device or topology data.
 */
export function useDeviceEvents() {
  const queryClient = useQueryClient();

  useEffect(() => {
    let es: EventSource | null = null;
    let cancelled = false;

    const connect = () => {
      if (cancelled) return;
      try {
        es = new EventSource(devicesApi.getEventsStreamUrl());
      } catch {
        return;
      }
      es.onmessage = (ev) => {
        try {
          const data = JSON.parse(ev.data);
          const t = data?.type;
          if (t === 'devices_refresh' || t === 'rescan_completed') {
            queryClient.invalidateQueries({ queryKey: ['devices'] });
            queryClient.invalidateQueries({ queryKey: ['topology'] });
          }
        } catch {
          // ignore malformed payloads
        }
      };
      es.onerror = () => {
        if (es) {
          es.close();
          es = null;
        }
        if (!cancelled) {
          // Reconnect with backoff so we recover from transient drops.
          window.setTimeout(connect, 5000);
        }
      };
    };

    connect();
    return () => {
      cancelled = true;
      if (es) es.close();
    };
  }, [queryClient]);
}
