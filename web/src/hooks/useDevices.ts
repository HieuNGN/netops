import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { devicesApi } from '../api';
import type { Device } from '../api';

export function useDevices() {
  const queryClient = useQueryClient();

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
    mutationFn: (data: { network_range: string; community?: string; method?: string; replace?: boolean }) =>
      devicesApi.rescan(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['devices'] });
      queryClient.invalidateQueries({ queryKey: ['topology'] });
    },
  });

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
  };
}