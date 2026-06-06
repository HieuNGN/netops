import { useState, useEffect, useRef } from 'react';
import { useAuth } from '../hooks/useAuth';
import { useNavigate, Navigate, Link } from 'react-router-dom';
import { Box, Key, Eye, EyeOff, Shield, User, Mail, ArrowRight, AlertTriangle } from 'lucide-react';

type Mode = 'signin' | 'signup';

export function LoginPage() {
  const { login, signup, token } = useAuth();
  const navigate = useNavigate();
  const [mode, setMode] = useState<Mode>('signin');

  // shared
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPw, setShowPw] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  // signup-only
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [confirm, setConfirm] = useState('');
  const [accepted, setAccepted] = useState(false);

  const usernameRef = useRef<HTMLInputElement>(null);
  useEffect(() => { usernameRef.current?.focus(); }, [mode]);

  if (token) return <Navigate to="/" replace />;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (mode === 'signup') {
      if (password !== confirm) { setError('Passwords do not match'); return; }
      if (!accepted) { setError('Accept the operator terms to continue'); return; }
      setLoading(true);
      try {
        await signup({ username, email, name, password });
        navigate('/');
    } catch (err) {
      setError(extractError(err, 'Sign up failed'));
    } finally { setLoading(false); }
    } else {
      setLoading(true);
      try { await login(username, password); navigate('/'); }
      catch (err) { setError(extractError(err, 'Invalid credentials')); }
      finally { setLoading(false); }
    }
  };

  function extractError(err: unknown, fallback: string): string {
    const data = (err as { response?: { data?: unknown } })?.response?.data;
    if (data && typeof data === 'object') {
      const detail = (data as { detail?: unknown }).detail;
      if (typeof detail === 'string') return detail;
      if (Array.isArray(detail) && detail.length > 0) {
        const first = detail[0] as { msg?: string; loc?: unknown[] };
        if (typeof first?.msg === 'string') {
          return first.msg.replace(/^Value error,\s*/i, '');
        }
      }
    }
    return fallback;
  }

  const switchMode = (m: Mode) => { setMode(m); setError(''); };

  return (
    <div className="min-h-screen w-full grid grid-cols-1 md:grid-cols-[1.1fr_1fr] bg-background text-foreground font-mono">
      <aside className="relative hidden md:flex flex-col justify-between p-10 border-r border-border bg-[#0a0a0a] text-[#f4f4f4] overflow-hidden">
        <div className="absolute inset-0 pointer-events-none opacity-[0.07]"
             style={{
               backgroundImage:
                 'repeating-linear-gradient(0deg, transparent 0 23px, #f4f4f4 23px 24px), repeating-linear-gradient(90deg, transparent 0 23px, #f4f4f4 23px 24px)',
             }} />
        <div className="relative z-10 flex items-center gap-3">
          <div className="w-10 h-10 grid place-items-center bg-thinkpad-red text-white">
            <Shield className="h-5 w-5" />
          </div>
          <div className="leading-tight">
            <div className="text-[10px] uppercase tracking-[0.3em] text-muted-foreground">netops / v1</div>
            <div className="text-sm font-bold uppercase">Operator Console</div>
          </div>
        </div>

        <div className="relative z-10 max-w-md">
          <div className="text-[10px] uppercase tracking-[0.3em] text-muted-foreground mb-3">
            // session {new Date().toISOString().slice(0, 10)} · node.alpha
          </div>
          <h2 className="text-3xl xl:text-4xl font-bold uppercase leading-[1.05] tracking-tight">
            Topology.<br />
            Devices.<br />
            <span className="text-destructive">Alarms.</span>
          </h2>
          <p className="mt-5 text-sm text-muted-foreground leading-relaxed">
            Discover, poll, and audit your routed fabric. SNMPv2c / v3, LLDP, service checks,
            and alert routing — one operator pane.
          </p>

          <div className="mt-8 grid grid-cols-3 gap-px bg-[#f4f4f4]/20 border border-[#f4f4f4]/20">
            {[
              { k: 'PROTO', v: 'SNMP' },
              { k: 'GRAPH', v: 'LLDP' },
              { k: 'ALERT', v: '24/7' },
            ].map((m) => (
              <div key={m.k} className="bg-[#0a0a0a] p-3">
                <div className="text-[9px] uppercase tracking-[0.25em] text-muted-foreground">{m.k}</div>
                <div className="text-sm font-bold mt-1">{m.v}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="relative z-10 text-[10px] uppercase tracking-[0.3em] text-muted-foreground flex items-center justify-between">
          <span>// build {import.meta.env.MODE === 'production' ? 'prod' : 'dev'}</span>
          <span>no cookies · jwt only</span>
        </div>
      </aside>

      <main className="flex items-center justify-center p-6 sm:p-10">
        <div className="w-full max-w-sm">
          <header className="mb-6 flex items-end justify-between border-b border-foreground dark:border-border pb-3">
            <div>
              <div className="text-[10px] uppercase tracking-[0.3em] text-muted-foreground dark:text-muted-foreground">
                {mode === 'signin' ? '> access.request' : '> account.create'}
              </div>
              <h1 className="text-2xl font-bold uppercase tracking-tight mt-1">
                {mode === 'signin' ? 'Sign in' : 'Create account'}
              </h1>
            </div>
            <div className="flex border border-foreground dark:border-border">
              {(['signin', 'signup'] as Mode[]).map((m) => (
                <button
                  key={m}
                  type="button"
                  onClick={() => switchMode(m)}
                  className={
                    'px-3 py-1.5 text-[10px] uppercase tracking-[0.2em] font-bold ' +
                    (mode === m
                      ? 'bg-thinkpad-red text-white'
                      : 'bg-transparent text-foreground hover:bg-surface-hover')
                  }
                >
                  {m === 'signin' ? 'Log in' : 'Sign up'}
                </button>
              ))}
            </div>
          </header>

          <form onSubmit={handleSubmit} className="space-y-4">
            {error && (
              <div className="flex items-start gap-2 p-3 bg-destructive/10 border-l-2 border-ring text-sm">
                <AlertTriangle className="h-4 w-4 mt-0.5 text-destructive shrink-0" />
                <span className="text-destructive">{error}</span>
              </div>
            )}

            {mode === 'signup' && (
              <>
                <Field
                  id="name"
                  label="Full name"
                  icon={<User className="h-4 w-4" />}
                  type="text"
                  value={name}
                  onChange={setName}
                  placeholder="Jane Operator"
                  autoComplete="name"
                />
                <Field
                  id="email"
                  label="Email"
                  icon={<Mail className="h-4 w-4" />}
                  type="email"
                  value={email}
                  onChange={setEmail}
                  placeholder="jane@example.com"
                  autoComplete="email"
                />
              </>
            )}

            <Field
              id="username"
              label="Username"
              icon={<Box className="h-4 w-4" />}
              type="text"
              value={username}
              onChange={setUsername}
              placeholder="admin"
              autoComplete="username"
              inputRef={usernameRef}
            />

            <div>
              <label className="block text-[10px] uppercase tracking-[0.25em] font-bold text-muted-foreground dark:text-muted-foreground mb-1">
                Password
              </label>
              <div className="relative">
                <Key className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <input
                  type={showPw ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete={mode === 'signin' ? 'current-password' : 'new-password'}
                  className="w-full pl-10 pr-10 py-2.5 bg-transparent border border-foreground dark:border-border focus:border-ring focus:ring-1 focus:ring-ring outline-none rounded-none"
                  placeholder="••••••••"
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowPw(!showPw)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-muted-foreground"
                  tabIndex={-1}
                >
                  {showPw ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
              {mode === 'signup' && (
                <p className="mt-1 text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
                  min 8 · upper + lower + digit + symbol
                </p>
              )}
            </div>

            {mode === 'signup' && (
              <>
                <div>
                  <label className="block text-[10px] uppercase tracking-[0.25em] font-bold text-muted-foreground dark:text-muted-foreground mb-1">
                    Confirm password
                  </label>
                  <div className="relative">
                    <Key className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                    <input
                      type={showPw ? 'text' : 'password'}
                      value={confirm}
                      onChange={(e) => setConfirm(e.target.value)}
                      autoComplete="new-password"
                      className="w-full pl-10 pr-3 py-2.5 bg-transparent border border-foreground dark:border-border focus:border-ring focus:ring-1 focus:ring-ring outline-none rounded-none"
                      placeholder="••••••••"
                      required
                    />
                  </div>
                </div>

                <label className="flex items-start gap-2 text-[11px] leading-snug text-muted-foreground dark:text-muted-foreground">
                  <input
                    type="checkbox"
                    checked={accepted}
                    onChange={(e) => setAccepted(e.target.checked)}
                    className="mt-0.5 h-3 w-3 accent-[#da1e28]"
                  />
                  <span>
                    I will operate this console responsibly and accept the{' '}
                    <Link to="/terms" className="underline underline-offset-2 hover:text-destructive">operator terms</Link>.
                  </span>
                </label>
              </>
            )}

            <button
              type="submit"
              disabled={loading}
              className="group w-full flex items-center justify-center gap-2 py-2.5 bg-thinkpad-red text-white uppercase tracking-[0.2em] text-xs font-bold hover:bg-thinkpad-red-hover disabled:opacity-50"
            >
              {loading
                ? (mode === 'signin' ? 'Authenticating...' : 'Provisioning...')
                : (mode === 'signin' ? 'Sign in' : 'Create account')}
              {!loading && <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />}
            </button>

            {mode === 'signin' && (
              <p className="text-center text-[10px] uppercase tracking-[0.25em] text-muted-foreground dark:text-muted-foreground pt-2">
                no account?{' '}
                <button type="button" onClick={() => switchMode('signup')}
                        className="text-destructive hover:underline underline-offset-2">
                  request access
                </button>
              </p>
            )}
          </form>
        </div>
      </main>
    </div>
  );
}

interface FieldProps {
  id: string;
  label: string;
  icon: React.ReactNode;
  type: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  autoComplete?: string;
  inputRef?: React.RefObject<HTMLInputElement | null>;
}

function Field({ id, label, icon, type, value, onChange, placeholder, autoComplete, inputRef }: FieldProps) {
  return (
    <div>
      <label htmlFor={id} className="block text-[10px] uppercase tracking-[0.25em] font-bold text-muted-foreground dark:text-muted-foreground mb-1">
        {label}
      </label>
      <div className="relative">
        <span className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground">{icon}</span>
        <input
          id={id}
          ref={inputRef}
          type={type}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          autoComplete={autoComplete}
          className="w-full pl-10 pr-3 py-2.5 bg-transparent border border-foreground dark:border-border focus:border-ring focus:ring-1 focus:ring-ring outline-none rounded-none"
          placeholder={placeholder}
          required
        />
      </div>
    </div>
  );
}

export default LoginPage;
