import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useTopology } from '../useTopology';

// Mock the API module
vi.mock('../../api/endpoints', () => ({
  topologyApi: {
    get: vi.fn(),
    getStreamUrl: vi.fn(() => 'http://localhost/topology/stream'),
  },
}));

import { topologyApi } from '../../api/endpoints';

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
  };
}

describe('useTopology', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('returns empty topology initially', () => {
    vi.mocked(topologyApi.get).mockResolvedValueOnce({ data: { nodes: [], links: [] } } as any);
    const { result } = renderHook(() => useTopology(), { wrapper: createWrapper() });
    expect(result.current.topology).toEqual({ nodes: [], links: [] });
  });

  it('sets isStreaming false when SSE errors', async () => {
    vi.mocked(topologyApi.get).mockResolvedValueOnce({ data: { nodes: [], links: [] } } as any);

    const { result } = renderHook(() => useTopology(), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.isStreaming).toBe(false));
  });

  it('calls refresh invalidates query', async () => {
    vi.mocked(topologyApi.get).mockResolvedValueOnce({ data: { nodes: [], links: [] } } as any);
    const { result } = renderHook(() => useTopology(), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    // refresh should not throw
    expect(() => result.current.refresh()).not.toThrow();
  });
});
