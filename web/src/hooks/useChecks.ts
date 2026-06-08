import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { checksApi, configApi } from '../api';
import type { ServiceCheck } from '../api';

export function useChecks() {
  const queryClient = useQueryClient();

  const { data: checks, isLoading, error } = useQuery({
    queryKey: ['checks'],
    queryFn: async () => {
      const response = await checksApi.list();
      return response.data;
    },
  });

  const { data: defaults } = useQuery({
    queryKey: ['check-defaults'],
    queryFn: async () => {
      const response = await configApi.checkDefaults();
      return response.data.check_intervals;
    },
    staleTime: 5 * 60_000,
  });

  const createMutation = useMutation({
    mutationFn: (data: {
      name: string;
      check_type: string;
      target: string;
      interval_seconds?: number;
      timeout_seconds?: number;
      config: Record<string, any>;
      enabled?: boolean;
    }) => checksApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['checks'] });
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<ServiceCheck> }) =>
      checksApi.update(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['checks'] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => checksApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['checks'] });
    },
  });

  const runMutation = useMutation({
    mutationFn: (id: string) => checksApi.run(id),
  });

  return {
    checks: checks || [],
    defaults: defaults || {},
    isLoading,
    error,
    createCheck: createMutation.mutateAsync,
    updateCheck: updateMutation.mutateAsync,
    deleteCheck: deleteMutation.mutateAsync,
    runCheck: runMutation.mutateAsync,
  };
}

export function useCheckResults(checkId: string) {
  const { data: results, isLoading } = useQuery({
    queryKey: ['check-results', checkId],
    queryFn: async () => {
      const response = await checksApi.results(checkId, 100);
      return response.data;
    },
    enabled: !!checkId,
  });

  return {
    results: results || [],
    isLoading,
  };
}
