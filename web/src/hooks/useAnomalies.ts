import { useQuery } from '@tanstack/react-query';
import { anomaliesApi } from '../api/endpoints';

export function useAnomalies() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['anomalies'],
    queryFn: async () => {
      const res = await anomaliesApi.list();
      return res.data.anomalies;
    },
    refetchInterval: 30000,
  });

  return {
    anomalies: data || [],
    isLoading,
    error,
    count: data?.length || 0,
  };
}
