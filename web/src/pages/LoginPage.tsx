import { useState } from 'react';
import { useAuth } from '../hooks/useAuth';
import { useNavigate, Navigate } from 'react-router-dom';
import { Box, Key, Eye, EyeOff, Shield } from 'lucide-react';

export function LoginPage() {
  const { login, token } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPw, setShowPw] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  if (token) return <Navigate to="/" replace />;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault(); setError(''); setLoading(true);
    try { await login(username, password); navigate('/'); }
    catch { setError('Invalid credentials'); }
    finally { setLoading(false); }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-white dark:bg-black">
      <div className="w-full max-w-sm p-8">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-12 h-12 bg-[#da1e28] rounded-sm mb-4">
            <Shield className="h-6 w-6 text-white" />
          </div>
          <h1 className="text-2xl font-bold text-[#161616] dark:text-white">NetOps</h1>
          <p className="text-sm text-[#525252] dark:text-[#a8a8a8] mt-1">Sign in to your account</p>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          {error && (
            <div className="p-3 bg-[#fff0f1] dark:bg-[#520408] border border-[#da1e28] rounded-sm text-sm text-[#da1e28]">{error}</div>
          )}
          <div>
            <label className="block text-sm font-medium text-[#161616] dark:text-[#a8a8a8] mb-1">Username</label>
            <div className="relative">
              <Box className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-[#a8a8a8]" />
              <input type="text" value={username} onChange={e => setUsername(e.target.value)}
                className="w-full pl-10 pr-3 py-2.5 border border-[#c6c6c6] dark:border-[#525252] bg-white dark:bg-[#262626] text-[#161616] dark:text-white rounded-sm focus:ring-1 focus:ring-[#da1e28] focus:border-[#da1e28] outline-none"
                placeholder="admin" required autoFocus />
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-[#161616] dark:text-[#a8a8a8] mb-1">Password</label>
            <div className="relative">
              <Key className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-[#a8a8a8]" />
              <input type={showPw ? 'text' : 'password'} value={password} onChange={e => setPassword(e.target.value)}
                className="w-full pl-10 pr-10 py-2.5 border border-[#c6c6c6] dark:border-[#525252] bg-white dark:bg-[#262626] text-[#161616] dark:text-white rounded-sm focus:ring-1 focus:ring-[#da1e28] focus:border-[#da1e28] outline-none"
                placeholder="••••••••" required />
              <button type="button" onClick={() => setShowPw(!showPw)} className="absolute right-3 top-1/2 -translate-y-1/2 text-[#a8a8a8] hover:text-[#525252]">
                {showPw ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
          </div>
          <button type="submit" disabled={loading}
            className="w-full py-2.5 bg-[#da1e28] text-white rounded-sm hover:bg-[#a3151f] disabled:opacity-50 font-medium">
            {loading ? 'Signing in...' : 'Sign in'}
          </button>
        </form>
      </div>
    </div>
  );
}
