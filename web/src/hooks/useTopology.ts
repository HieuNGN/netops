import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';
import { topologyApi } from '../api';
import type { TopologyData } from '../api';

export function useTopology() {
  const queryClient = useQueryClient();
  const eventSourceRef = useRef<EventSource | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Fetch initial topology
  const { data, isLoading, error } = useQuery({
    queryKey: ['topology'],
    queryFn: async () => {
      const response = await topologyApi.get();
      return response.data;
    },
    refetchInterval: 30000, // Refetch every 30 seconds
  });

  // Setup SSE connection for real-time updates
  useEffect(() => {
    const connectStream = () => {
      const streamUrl = topologyApi.getStreamUrl();
      eventSourceRef.current = new EventSource(streamUrl);

      eventSourceRef.current.onmessage = (event) => {
        const data = JSON.parse(event.data) as {
          type: string;
          topology: TopologyData;
          changes?: any;
        };

        if (data.type === 'initial' || data.type === 'topology_change') {
          queryClient.setQueryData(['topology'], data.topology);
          setIsStreaming(true);
          setLastUpdate(new Date());
        }
      };

      eventSourceRef.current.onerror = () => {
        console.error('Topology stream connection error, attempting reconnect...');
        setIsStreaming(false);
        eventSourceRef.current?.close();

        // Exponential backoff: retry after 3s, then 6s, then 12s, max 30s
        const backoffDelay = Math.min(30000, 3000 * (1 + Math.random()));
        reconnectTimeoutRef.current = setTimeout(connectStream, backoffDelay);
      };

      eventSourceRef.current.onopen = () => {
        console.log('Topology stream connected');
        setIsStreaming(true);
      };
    };

    connectStream();

    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      eventSourceRef.current?.close();
    };
  }, [queryClient]);

  return {
    topology: data || { nodes: [], links: [] },
    isLoading,
    error,
    isStreaming,
    lastUpdate,
    refresh: () => queryClient.invalidateQueries({ queryKey: ['topology'] }),
  };
}
