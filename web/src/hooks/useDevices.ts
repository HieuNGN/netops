import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { devicesApi } from '../api';
import type { Device } from '../api';
import { useDeviceEvents } from './useDeviceEvents';

export interface ScanLogEntry {
  ip_address: string;
  method: 'snmp' | 'ping' | 'port';
  sys_descr: string;
  is_new: boolean;
  timestamp: number;
}

export function useDevices() {
  const queryClient = useQueryClient();
  const [scanLog, setScanLog] = useState<ScanLogEntry[]>([]);
  const [scanProgress, setScanProgress] = useState({ scanned: 0, found: 0, by_method: { snmp: 0, ping: 0, port: 0 } });

  useDeviceEvents({
    onDeviceFound: (e) => {
      setScanLog(prev => [...prev, {
        ip_address: e.ip_address,
        method: e.method,
        sys_descr: e.sys_descr,
        is_new: e.is_new,
        timestamp: Date.now(),
      }]);
      setScanProgress(prev => ({
        ...prev,
        found: prev.found + 1,
        by_method: {
          ...prev.by_method,
          [e.method]: (prev.by_method[e.method] || 0) + 1,
        },
      }));
    },
  });

  const { data: devices, isLoading, error } = useQuery({
    queryKey: ['devices'],
    queryFn: async () => {
      const response = await devicesApi.list();
      return response.data;
    },
  });

  const createMutation = useMutation({
    mutationFn: (data: { name: string; ip_address: string; community: string }) =>
      devicesApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['devices'] });
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<Device> }) =>
      devicesApi.update(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['devices'] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => devicesApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['devices'] });
      queryClient.invalidateQueries({ queryKey: ['topology'] });
    },
  });

  const discoverMutation = useMutation({
    mutationFn: (data: { network_range: string; community?: string; method?: string }) =>
      devicesApi.discover(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['devices'] });
      queryClient.invalidateQueries({ queryKey: ['topology'] });
    },
  });

  const rescanMutation = useMutation({
    mutationFn: (data: {
      network_range: string;
      community?: string;
      method?: string;
      mode?: 'merge' | 'replace';
    }) => devicesApi.rescan(data),
    onSuccess: (data) => {
      setScanProgress(prev => ({
        ...prev,
        scanned: data?.data?.scanned || prev.scanned,
      }));
      queryClient.invalidateQueries({ queryKey: ['devices'] });
      queryClient.invalidateQueries({ queryKey: ['topology'] });
    },
  });

  const clearScanLog = () => {
    setScanLog([]);
    setScanProgress({ scanned: 0, found: 0, by_method: { snmp: 0, ping: 0, port: 0 } });
  };

  return {
    devices: devices || [],
    isLoading,
    error,
    createDevice: createMutation.mutateAsync,
    updateDevice: updateMutation.mutateAsync,
    deleteDevice: deleteMutation.mutateAsync,
    discoverNetwork: discoverMutation.mutateAsync,
    rescanNetwork: rescanMutation.mutateAsync,
    isRescanning: rescanMutation.isPending,
    isDiscovering: discoverMutation.isPending,
    scanLog,
    scanProgress,
    clearScanLog,
  };
}