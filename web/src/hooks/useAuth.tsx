import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react';
import apiClient from '../api/client';

interface AuthState {
  token: string | null;
  username: string | null;
  email: string | null;
  name: string | null;
  role: string | null;
  loading: boolean;
  isAuthenticated: boolean;
  login: (username: string, password: string) => Promise<void>;
  signup: (data: { username: string; email: string; name: string; password: string }) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthState>({
  token: null, username: null, email: null, name: null, role: null, loading: true, isAuthenticated: false,
  login: async () => {}, signup: async () => {}, logout: () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(localStorage.getItem('token'));
  const [username, setUsername] = useState<string | null>(null);
  const [email, setEmail] = useState<string | null>(null);
  const [name, setName] = useState<string | null>(null);
  const [role, setRole] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (token) {
      apiClient.defaults.headers.common['Authorization'] = `Bearer ${token}`;
      apiClient.get('/api/auth/me')
        .then(r => {
          setUsername(r.data.username);
          setEmail(r.data.email ?? null);
          setName(r.data.name ?? null);
          setRole(r.data.role);
        })
        .catch(() => { setToken(null); localStorage.removeItem('token'); })
        .finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, [token]);

  const applyAuth = useCallback((data: { token: string; username: string; email?: string | null; name?: string | null; role?: string | null }) => {
    localStorage.setItem('token', data.token);
    apiClient.defaults.headers.common['Authorization'] = `Bearer ${data.token}`;
    setToken(data.token);
    setUsername(data.username);
    setEmail(data.email ?? null);
    setName(data.name ?? null);
    setRole(data.role ?? null);
    localStorage.setItem('netops_post_signup_banner', '1');
  }, []);

  const login = useCallback(async (u: string, p: string) => {
    const r = await apiClient.post('/api/auth/login', { username: u, password: p });
    applyAuth(r.data);
  }, [applyAuth]);

  const signup = useCallback(async (data: { username: string; email: string; name: string; password: string }) => {
    const r = await apiClient.post('/api/auth/signup', data);
    applyAuth(r.data);
  }, [applyAuth]);

  const logout = useCallback(() => {
    localStorage.removeItem('token');
    localStorage.removeItem('netops_post_signup_banner');
    delete apiClient.defaults.headers.common['Authorization'];
    setToken(null); setUsername(null); setEmail(null); setName(null); setRole(null);
  }, []);

  return (
    <AuthContext.Provider value={{ token, username, email, name, role, loading, isAuthenticated: !!token, login, signup, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() { return useContext(AuthContext); }
