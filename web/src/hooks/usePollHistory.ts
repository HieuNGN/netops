import { useQuery } from '@tanstack/react-query';
import { healthApi } from '../api';

export interface PollHistoryEntry {
  id: number;
  device_id: string;
  status: string;
  response_time_ms: number;
  error: string;
  polled_at: string;
  ip_address?: string;
  name?: string;
}

export function usePollHistory(limit: number = 100) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['pollHistory', limit],
    queryFn: async () => {
      const response = await healthApi.pollHistory(limit);
      return (response.data as PollHistoryEntry[]) || [];
    },
    refetchInterval: 30000,
  });

  return {
    history: data || [],
    isLoading,
    error,
  };
}
