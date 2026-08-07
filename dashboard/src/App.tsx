import { useState } from 'react';
import Login from './views/Login';
import Dashboard from './views/Dashboard';
import MarketOverview from './views/MarketOverview';
import Tokens from './views/Tokens';
import Predictions from './views/Predictions';
import Strategies from './views/Strategies';
import RiskDashboard from './views/RiskDashboard';
import Settings from './views/Settings';
import Transactions from './views/Transactions';
import Performance from './views/Performance';
import LatestCycle from './views/LatestCycle';
import PendingApprovals from './views/PendingApprovals';
import BacktestRuns from './views/BacktestRuns';
import ResearchWorkspace from './views/ResearchWorkspace';
import Sidebar from './components/Sidebar';
import { clearToken, hasToken } from './api/auth';

function App() {
  const [isLoggedIn, setIsLoggedIn] = useState(hasToken);
  const [view, setView] = useState('dashboard');

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
          {view === 'transactions' && <Transactions />}
          {view === 'performance' && <Performance />}
          {view === 'market' && <MarketOverview />}
          {view === 'tokens' && <Tokens />}
          {view === 'predictions' && <Predictions />}
          {view === 'strategies' && <Strategies />}
          {view === 'risk' && <RiskDashboard />}
          {view === 'settings' && <Settings />}
          {view === 'cycle' && <LatestCycle />}
          {view === 'approvals' && <PendingApprovals />}
          {view === 'backtest' && <BacktestRuns />}
          {view === 'workspace' && <ResearchWorkspace />}
        </div>
      </main>
    </div>
  );
}
export default App;
