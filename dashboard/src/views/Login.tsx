import { useState } from 'react';
import { setToken } from '../api/auth';
import { Button, Input } from '../components/ui';

function Login({ onLogin }: { onLogin: () => void }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const submit = () => {
    setError(null);
    setLoading(true);
    const path = mode === 'login' ? '/api/v1/auth/login' : '/api/v1/auth/register';
    fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    })
      .then(async (r) => {
        const data = await r.json();
        if (!r.ok) throw new Error(data.detail || `HTTP ${r.status}`);
        return data;
      })
      .then((data) => {
        if (mode === 'register') {
          setMode('login');
          setError(`Registered as ${data.role}. Now log in.`);
          return;
        }
        setToken(data.access_token);
        onLogin();
      })
      .catch((e) => setError(String(e.message || e)))
      .finally(() => setLoading(false));
  };

  return (
    <div className="min-h-screen bg-canvas flex flex-col items-center justify-center px-4 relative overflow-hidden">
      <div
        className="absolute -top-32 -left-24 w-[32rem] h-[32rem] rounded-full opacity-40 blur-3xl pointer-events-none"
        style={{ background: "radial-gradient(circle, var(--color-accent-soft), transparent 70%)" }}
      />
      <div
        className="absolute -bottom-40 -right-32 w-[28rem] h-[28rem] rounded-full opacity-30 blur-3xl pointer-events-none"
        style={{ background: "radial-gradient(circle, var(--color-rise-soft), transparent 70%)" }}
      />

      <div className="relative w-full max-w-sm">
        <div className="text-center mb-8">
          <div className="w-10 h-10 rounded-2xl bg-accent mx-auto mb-4 shadow-layer-2" />
          <h1 className="text-2xl font-semibold text-ink tracking-tight">AI Quant Research</h1>
          <p className="text-ink-soft text-sm mt-1">Cognitive Core</p>
        </div>

        <div className="bg-surface border border-line rounded-xl shadow-layer-3 p-7">
          <div className="flex mb-6 bg-canvas-soft rounded-lg p-1">
            <button
              onClick={() => setMode('login')}
              className={`flex-1 py-1.5 rounded-md text-sm font-medium ${mode === 'login' ? 'bg-surface shadow-layer-1 text-ink' : 'text-ink-soft'}`}
            >
              Sign in
            </button>
            <button
              onClick={() => setMode('register')}
              className={`flex-1 py-1.5 rounded-md text-sm font-medium ${mode === 'register' ? 'bg-surface shadow-layer-1 text-ink' : 'text-ink-soft'}`}
            >
              Register
            </button>
          </div>

          <div className="flex flex-col gap-3">
            <Input value={username} onChange={setUsername} placeholder="Username" />
            <Input value={password} onChange={setPassword} placeholder="Password" type="password" />
            {error && <div className="text-fall text-xs bg-fall-soft rounded-lg px-3 py-2">{error}</div>}
            <Button onClick={submit} disabled={loading} className="w-full mt-1">
              {loading ? 'Please wait…' : mode === 'login' ? 'Sign in' : 'Create account'}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
export default Login;
