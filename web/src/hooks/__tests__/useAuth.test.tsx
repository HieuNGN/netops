import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { AuthProvider, useAuth } from '../useAuth';
import apiClient from '../../api/client';

// Mock apiClient
vi.mock('../../api/client', () => ({
  default: {
    post: vi.fn(),
    get: vi.fn(),
    defaults: {
      headers: {
        common: {} as Record<string, string>,
      },
    },
  },
}));

function wrapper({ children }: { children: React.ReactNode }) {
  return <AuthProvider>{children}</AuthProvider>;
}

describe('useAuth', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });

  it('initial state: not authenticated, loading then false', async () => {
    vi.mocked(apiClient.get).mockRejectedValueOnce({ response: { status: 401 } });
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.isAuthenticated).toBe(false);
  });

  it('login sets authenticated and user info', async () => {
    // Mount call rejects (not logged in)
    vi.mocked(apiClient.get).mockRejectedValueOnce({ response: { status: 401 } });
    // Login then calls get /api/auth/me
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: { username: 'admin', role: 'admin' },
    } as any);
    vi.mocked(apiClient.post).mockResolvedValueOnce({} as any);

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.login('admin', 'password');
    });

    expect(result.current.isAuthenticated).toBe(true);
    expect(result.current.username).toBe('admin');
  });

  it('logout clears state', async () => {
    // Mount call rejects
    vi.mocked(apiClient.get).mockRejectedValueOnce({ response: { status: 401 } });
    // Login get call
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: { username: 'admin', role: 'admin' },
    } as any);
    vi.mocked(apiClient.post).mockResolvedValueOnce({} as any); // login post

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(async () => {
      await result.current.login('admin', 'password');
    });

    // Logout post
    vi.mocked(apiClient.post).mockResolvedValueOnce({} as any);
    await act(async () => {
      await result.current.logout();
    });

    expect(result.current.isAuthenticated).toBe(false);
    expect(result.current.username).toBeNull();
    expect(localStorage.getItem('token')).toBeNull();
  });
});
