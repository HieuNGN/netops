import { useQuery } from '@tanstack/react-query';
import { topologyApi } from '../api';

interface UseTopologyHistoryOptions {
  limit?: number;
  event_type?: string;
  from_time?: string;
  to_time?: string;
  offset?: number;
}

export function useTopologyHistory(options: UseTopologyHistoryOptions = {}) {
  const { limit = 100, event_type, from_time, to_time, offset = 0 } = options;
  const { data, isLoading, error } = useQuery({
    queryKey: ['topologyHistory', limit, event_type, from_time, to_time, offset],
    queryFn: async () => {
      const response = await topologyApi.history(limit, event_type, from_time, to_time, offset);
      return response.data;
    },
    refetchInterval: 30000,
  });

  return {
    events: data?.events || [],
    total: data?.total || 0,
    isLoading,
    error,
  };
}
