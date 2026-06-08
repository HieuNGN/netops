import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react';
import apiClient from '../api/client';

interface AuthState {
  username: string | null;
  email: string | null;
  name: string | null;
  role: string | null;
  loading: boolean;
  isAuthenticated: boolean;
  login: (username: string, password: string) => Promise<void>;
  signup: (data: { username: string; email: string; name: string; password: string }) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthState>({
  username: null, email: null, name: null, role: null, loading: true, isAuthenticated: false,
  login: async () => {}, signup: async () => {}, logout: async () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [username, setUsername] = useState<string | null>(null);
  const [email, setEmail] = useState<string | null>(null);
  const [name, setName] = useState<string | null>(null);
  const [role, setRole] = useState<string | null>(null);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [loading, setLoading] = useState(true);

  const fetchMe = useCallback(async () => {
    try {
      const r = await apiClient.get('/api/auth/me');
      setUsername(r.data.username);
      setEmail(r.data.email ?? null);
      setName(r.data.name ?? null);
      setRole(r.data.role ?? null);
      setIsAuthenticated(true);
    } catch {
      setUsername(null); setEmail(null); setName(null); setRole(null);
      setIsAuthenticated(false);
    }
  }, []);

  useEffect(() => {
    fetchMe().finally(() => setLoading(false));
  }, [fetchMe]);

  const applyUser = useCallback((data: { username: string; email?: string | null; name?: string | null; role?: string | null }) => {
    setUsername(data.username);
    setEmail(data.email ?? null);
    setName(data.name ?? null);
    setRole(data.role ?? null);
    setIsAuthenticated(true);
    localStorage.setItem('netops_post_signup_banner', '1');
  }, []);

  const login = useCallback(async (u: string, p: string) => {
    await apiClient.post('/api/auth/login', { username: u, password: p });
    const r = await apiClient.get('/api/auth/me');
    applyUser(r.data);
  }, [applyUser]);

  const signup = useCallback(async (data: { username: string; email: string; name: string; password: string }) => {
    await apiClient.post('/api/auth/signup', data);
    const r = await apiClient.get('/api/auth/me');
    applyUser(r.data);
  }, [applyUser]);

  const logout = useCallback(async () => {
    await apiClient.post('/api/auth/logout').catch(() => {});
    delete apiClient.defaults.headers.common['Authorization'];
    localStorage.removeItem('netops_post_signup_banner');
    setUsername(null); setEmail(null); setName(null); setRole(null);
    setIsAuthenticated(false);
  }, []);

  return (
    <AuthContext.Provider value={{ username, email, name, role, loading, isAuthenticated, login, signup, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() { return useContext(AuthContext); }
