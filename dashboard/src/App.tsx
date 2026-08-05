import { useState } from 'react';
import Login from './views/Login';
import MarketOverview from './views/MarketOverview';
import Predictions from './views/Predictions';
import LivePredictions from './views/LivePredictions';
import Strategies from './views/Strategies';
import RiskDashboard from './views/RiskDashboard';
import AIReasoning from './views/AIReasoning';
import LatestCycle from './views/LatestCycle';
import PendingApprovals from './views/PendingApprovals';
import ExperimentList from './views/ExperimentList';
import ReplayView from './views/ReplayView';
import BacktestRuns from './views/BacktestRuns';
import DecisionExplain from './views/DecisionExplain';
import ResearchWorkspace from './views/ResearchWorkspace';
import Sidebar from './components/Sidebar';
import { clearToken } from './api/auth';

function App() {
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [view, setView] = useState('live');

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
          {view === 'live' && <LivePredictions />}
          {view === 'market' && <MarketOverview />}
          {view === 'predictions' && <Predictions />}
          {view === 'strategies' && <Strategies />}
          {view === 'risk' && <RiskDashboard />}
          {view === 'reasoning' && <AIReasoning />}
          {view === 'cycle' && <LatestCycle />}
          {view === 'approvals' && <PendingApprovals />}
          {view === 'experiments' && <ExperimentList />}
          {view === 'replay' && <ReplayView />}
          {view === 'backtest' && <BacktestRuns />}
          {view === 'explain' && <DecisionExplain />}
          {view === 'workspace' && <ResearchWorkspace />}
        </div>
      </main>
    </div>
  );
}
export default App;
