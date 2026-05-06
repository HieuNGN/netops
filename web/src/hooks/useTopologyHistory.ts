import { useQuery } from '@tanstack/react-query';
import { topologyApi } from '../api';
import type { TopologyHistoryEvent } from '../api';

export function useTopologyHistory(limit = 100) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['topologyHistory', limit],
    queryFn: async () => {
      const response = await topologyApi.history(limit);
      return response.data.events as TopologyHistoryEvent[];
    },
    refetchInterval: 30000,
  });

  return {
    events: data || [],
    isLoading,
    error,
  };
}
