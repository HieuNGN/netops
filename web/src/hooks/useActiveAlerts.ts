import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { alertsApi } from '../api';
import type { ActiveAlert } from '../api';

export function useActiveAlerts() {
  const queryClient = useQueryClient();

  const { data, isLoading, error } = useQuery({
    queryKey: ['activeAlerts'],
    queryFn: async () => {
      const response = await alertsApi.active();
      return response.data.alerts as ActiveAlert[];
    },
    refetchInterval: 15000,
  });

  const acknowledgeMutation = useMutation({
    mutationFn: (key: string) => alertsApi.acknowledge(key),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['activeAlerts'] });
    },
  });

  const resolveMutation = useMutation({
    mutationFn: (key: string) => alertsApi.resolve(key),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['activeAlerts'] });
    },
  });

  return {
    alerts: data || [],
    isLoading,
    error,
    acknowledge: acknowledgeMutation.mutateAsync,
    resolve: resolveMutation.mutateAsync,
    isAcknowledging: acknowledgeMutation.isPending,
    isResolving: resolveMutation.isPending,
  };
}
