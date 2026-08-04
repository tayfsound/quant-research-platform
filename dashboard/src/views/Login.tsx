import { useState } from 'react';
import { setToken } from '../api/auth';

function Login({ onLogin }: { onLogin: () => void }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [error, setError] = useState<string | null>(null);

  const submit = () => {
    setError(null);
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
      .catch((e) => setError(String(e.message || e)));
  };

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 flex flex-col items-center justify-center">
      <h1 className="text-4xl font-bold mb-2">AI Quant Research Platform</h1>
      <p className="text-gray-400 mb-8">{mode === 'login' ? 'Sign in' : 'Create an account'}</p>

      <div className="flex flex-col gap-3 w-72">
        <input
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          placeholder="username"
          className="px-3 py-2 rounded bg-gray-800 text-sm"
        />
        <input
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="password"
          type="password"
          className="px-3 py-2 rounded bg-gray-800 text-sm"
        />
        {error && <div className="text-red-400 text-xs">{error}</div>}
        <button
          onClick={submit}
          className="px-8 py-3 bg-indigo-600 hover:bg-indigo-500 rounded-lg text-lg font-semibold transition"
        >
          {mode === 'login' ? 'Login' : 'Register'}
        </button>
        <button
          onClick={() => setMode(mode === 'login' ? 'register' : 'login')}
          className="text-xs text-gray-400 hover:text-gray-200"
        >
          {mode === 'login' ? "No account? Register" : 'Have an account? Login'}
        </button>
      </div>
    </div>
  );
}
export default Login;
