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
import FeatureIC from './views/FeatureIC';
import SelfModel from './views/SelfModel';
import CausalInference from './views/CausalInference';
import Sidebar from './components/Sidebar';
import { clearToken, hasToken } from './api/auth';

function App() {
  const [isLoggedIn, setIsLoggedIn] = useState(hasToken);
  const [view, setView] = useState('dashboard');
  // Faz 266: kullanıcı isteği — Transactions'ta bir işlem satırına
  // tıklayınca direkt o varlığın grafiğine gitsin. MarketOverview kendi
  // "seçili sembol" durumunu kendi içinde tutuyor (App.tsx'in "view"
  // mantığıyla aynı basit desen) — dışarıdan bir sembol "aşılamak" için
  // bunu buraya taşıyoruz.
  //
  // Kullanıcı bulgusu (sonraki bulgu): Tokens sayfası watchlist dışı
  // sembollerde (ör. Pump-Fade'in açtığı PORTALUSDT) 404 veriyordu VE
  // zaten gerçek bir mum grafiği hiç göstermiyordu. MarketOverview HER
  // sembol için (watchlist'te olsun olmasın, RoutingProvider gerçek
  // veriyi doğrudan borsadan çekiyor) gerçek bir candlestick grafiği +
  // order book + haber duyarlılığı gösteriyor — "her zaman market
  // bilgisi veren bir sayfa" isteğine uyan asıl hedef burası.
  const [tokenDetailSymbol, setTokenDetailSymbol] = useState<string | null>(null);

  const navigateToToken = (symbol: string) => {
    setTokenDetailSymbol(symbol);
    setView('market');
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
          {view === 'market' && <MarketOverview initialSymbol={tokenDetailSymbol} onSymbolConsumed={() => setTokenDetailSymbol(null)} />}
          {view === 'tokens' && <Tokens />}
          {view === 'predictions' && <Predictions />}
          {view === 'strategies' && <Strategies />}
          {view === 'settings' && <Settings />}
          {view === 'approvals' && <PendingApprovals />}
          {view === 'backtest' && <BacktestRuns />}
          {view === 'workspace' && <ResearchWorkspace />}
          {view === 'llm-critic' && <LLMCritic />}
          {view === 'feature-ic' && <FeatureIC />}
          {view === 'self-model' && <SelfModel />}
          {view === 'causal-inference' && <CausalInference />}
        </div>
      </main>
    </div>
  );
}
export default App;
