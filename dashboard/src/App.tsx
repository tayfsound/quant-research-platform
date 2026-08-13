import { useState } from 'react';
import Login from './views/Login';
import Dashboard from './views/Dashboard';
import MarketOverview from './views/MarketOverview';
import Tokens from './views/Tokens';
import Predictions from './views/Predictions';
import Strategies from './views/Strategies';
import Settings from './views/Settings';
import Transactions from './views/Transactions';
import PendingApprovals from './views/PendingApprovals';
import BacktestRuns from './views/BacktestRuns';
import ResearchWorkspace from './views/ResearchWorkspace';
import LLMCritic from './views/LLMCritic';
import Sidebar from './components/Sidebar';
import { clearToken, hasToken } from './api/auth';

function App() {
  const [isLoggedIn, setIsLoggedIn] = useState(hasToken);
  const [view, setView] = useState('dashboard');
  // Faz 266: kullanıcı isteği — Transactions'ta bir işlem satırına
  // tıklayınca direkt o varlığın grafiğine (Tokens sayfasındaki detay
  // görünümü) gitsin. Tokens kendi "seçili sembol" durumunu kendi
  // içinde tutuyor (App.tsx'in "view" mantığıyla aynı basit desen) —
  // dışarıdan bir sembol "aşılamak" için bunu buraya taşıyoruz.
  const [tokenDetailSymbol, setTokenDetailSymbol] = useState<string | null>(null);

  const navigateToToken = (symbol: string) => {
    setTokenDetailSymbol(symbol);
    setView('tokens');
  };

  if (!isLoggedIn) {
    return <Login onLogin={() => setIsLoggedIn(true)} />;
  }

  const handleLogout = () => {
    clearToken();
    setIsLoggedIn(false);
  };

  return (
    <div className="min-h-screen bg-canvas text-ink flex">
      <Sidebar current={view} onChange={setView} onLogout={handleLogout} />
      <main className="flex-1 min-w-0 overflow-x-auto">
        <div className="max-w-6xl mx-auto px-8 py-8">
          {view === 'dashboard' && <Dashboard />}
          {view === 'transactions' && <Transactions onSelectSymbol={navigateToToken} />}
          {view === 'market' && <MarketOverview />}
          {view === 'tokens' && <Tokens initialSymbol={tokenDetailSymbol} onSymbolConsumed={() => setTokenDetailSymbol(null)} />}
          {view === 'predictions' && <Predictions />}
          {view === 'strategies' && <Strategies />}
          {view === 'settings' && <Settings />}
          {view === 'approvals' && <PendingApprovals />}
          {view === 'backtest' && <BacktestRuns />}
          {view === 'workspace' && <ResearchWorkspace />}
          {view === 'llm-critic' && <LLMCritic />}
        </div>
      </main>
    </div>
  );
}
export default App;
