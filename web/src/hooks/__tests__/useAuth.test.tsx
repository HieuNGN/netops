import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { AuthProvider, useAuth } from '../useAuth';
import apiClient from '../../api/client';

// Mock apiClient
vi.mock('../../api/client', () => ({
  default: {
    defaults: { headers: { common: {} as Record<string, string> } },
    post: vi.fn(),
    get: vi.fn(),
  },
}));

function wrapper({ children }: { children: React.ReactNode }) {
  return <AuthProvider>{children}</AuthProvider>;
}

describe('useAuth', () => {
  beforeEach(() => {
    localStorage.clear();
    (apiClient.defaults.headers.common as Record<string, string>) = {};
    vi.clearAllMocks();
  });

  it('initial state: not authenticated, loading then false', async () => {
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.token).toBeNull();
    expect(result.current.isAuthenticated).toBe(false);
  });

  it('login stores token and sets header', async () => {
    vi.mocked(apiClient.post).mockResolvedValueOnce({
      data: { token: 'abc123', username: 'admin', role: 'admin' },
    } as any);
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: { username: 'admin', role: 'admin' },
    } as any);

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.login('admin', 'password');
    });

    expect(localStorage.getItem('token')).toBe('abc123');
    expect(apiClient.defaults.headers.common['Authorization']).toBe('Bearer abc123');
    expect(result.current.username).toBe('admin');
  });

  it('logout clears token and header', async () => {
    vi.mocked(apiClient.post).mockResolvedValueOnce({
      data: { token: 'abc123', username: 'admin', role: 'admin' },
    } as any);
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: { username: 'admin', role: 'admin' },
    } as any);

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(async () => {
      await result.current.login('admin', 'password');
    });

    act(() => result.current.logout());
    expect(localStorage.getItem('token')).toBeNull();
    expect(apiClient.defaults.headers.common['Authorization']).toBeUndefined();
    expect(result.current.token).toBeNull();
  });
});
