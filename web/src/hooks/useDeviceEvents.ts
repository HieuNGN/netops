import { useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { devicesApi } from '../api';

export interface ProfileGuessedEvent {
  type: 'profile_guessed';
  profile: 'homelab' | 'small_business' | 'datacenter';
  device_count: number;
  confirmed: boolean;
}

export interface NetworkChangedEvent {
  type: 'network_changed';
  old_cidr: string | null;
  old_gateway: string | null;
  new_cidr: string | null;
  new_gateway: string | null;
  source?: 'startup' | 'watcher';
}

export interface DeviceStatusEvent {
  type: 'device_online' | 'device_offline';
  device_id: string;
  ip_address: string;
  name: string;
  old_status: string | null;
  new_status: string;
  error?: string;
  response_time_ms: number;
}

export interface DeviceFoundEvent {
  type: 'device_found';
  ip_address: string;
  method: 'snmp' | 'ping' | 'port';
  sys_descr: string;
  is_new: boolean;
  total: number;
}

export interface DeviceEventsOptions {
  onProfileGuessed?: (e: ProfileGuessedEvent) => void;
  onNetworkChanged?: (e: NetworkChangedEvent) => void;
  onDeviceStatusChange?: (e: DeviceStatusEvent) => void;
  onDeviceFound?: (e: DeviceFoundEvent) => void;
}

/**
 * Subscribe to /api/events/stream SSE and:
 *   - invalidate devices/topology queries on refresh events
 *   - forward typed events to optional callbacks
 */
export function useDeviceEvents(options: DeviceEventsOptions = {}) {
  const queryClient = useQueryClient();
  const {
    onProfileGuessed,
    onNetworkChanged,
    onDeviceStatusChange,
    onDeviceFound,
  } = options;

  useEffect(() => {
    let es: EventSource | null = null;
    let cancelled = false;

    const connect = () => {
      if (cancelled) return;
      try {
        es = new EventSource(devicesApi.getEventsStreamUrl(), { withCredentials: true });
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
          } else if (t === 'device_online' || t === 'device_offline') {
            queryClient.invalidateQueries({ queryKey: ['devices'] });
            queryClient.invalidateQueries({ queryKey: ['topology'] });
            onDeviceStatusChange?.(data as DeviceStatusEvent);
          } else if (t === 'device_found') {
            onDeviceFound?.(data as DeviceFoundEvent);
          } else if (t === 'profile_guessed') {
            queryClient.invalidateQueries({ queryKey: ['config-profiles'] });
            onProfileGuessed?.(data as ProfileGuessedEvent);
          } else if (t === 'network_changed') {
            queryClient.invalidateQueries({ queryKey: ['networks'] });
            onNetworkChanged?.(data as NetworkChangedEvent);
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
          window.setTimeout(connect, 5000);
        }
      };
    };

    connect();
    return () => {
      cancelled = true;
      if (es) es.close();
    };
  }, [queryClient, onProfileGuessed, onNetworkChanged, onDeviceStatusChange, onDeviceFound]);
}
