import { useState } from 'react';
import reactLogo from '../assets/react.svg';
import viteLogo from '/vite.svg';

function Login({ onLogin }: { onLogin: () => void }) {
  const [count, setCount] = useState(0);

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 flex flex-col items-center justify-center">
      <div className="flex gap-8 mb-8">
        <a href="https://vite.dev" target="_blank">
          <img src={viteLogo} className="h-24 hover:scale-110 transition" alt="Vite logo" />
        </a>
        <a href="https://react.dev" target="_blank">
          <img src={reactLogo} className="h-24 hover:scale-110 transition" alt="React logo" />
        </a>
      </div>
      <h1 className="text-4xl font-bold mb-4">AI Quant Research Platform</h1>
      <p className="text-gray-400 mb-8">Institutional-grade AI/ML trading research</p>
      <div className="flex gap-4 items-center mb-6">
        <button
          className="px-4 py-2 bg-gray-800 rounded hover:bg-gray-700 transition"
          onClick={() => setCount(count + 1)}
        >
          Count: {count}
        </button>
      </div>
      <button
        className="px-8 py-3 bg-indigo-600 hover:bg-indigo-500 rounded-lg text-lg font-semibold transition"
        onClick={onLogin}
      >
        Login
      </button>
    </div>
  );
}
export default Login;
