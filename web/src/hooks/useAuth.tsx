import { createContext, useContext, useState, useEffect, ReactNode, useCallback } from 'react';
import apiClient from '../api/client';

interface AuthState {
  token: string | null;
  username: string | null;
  role: string | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthState>({
  token: null, username: null, role: null, loading: true,
  login: async () => {}, logout: () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(localStorage.getItem('token'));
  const [username, setUsername] = useState<string | null>(null);
  const [role, setRole] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (token) {
      apiClient.defaults.headers.common['Authorization'] = `Bearer ${token}`;
      apiClient.get('/api/auth/me')
        .then(r => { setUsername(r.data.username); setRole(r.data.role); })
        .catch(() => { setToken(null); localStorage.removeItem('token'); })
        .finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, [token]);

  const login = useCallback(async (u: string, p: string) => {
    const r = await apiClient.post('/api/auth/login', { username: u, password: p });
    const t = r.data.token;
    localStorage.setItem('token', t);
    apiClient.defaults.headers.common['Authorization'] = `Bearer ${t}`;
    setToken(t);
    setUsername(r.data.username);
    setRole(r.data.role);
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem('token');
    delete apiClient.defaults.headers.common['Authorization'];
    setToken(null); setUsername(null); setRole(null);
  }, []);

  return (
    <AuthContext.Provider value={{ token, username, role, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() { return useContext(AuthContext); }
