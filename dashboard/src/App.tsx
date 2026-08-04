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
import NavBar from './components/NavBar';

function App() {
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [view, setView] = useState('live');

  if (!isLoggedIn) {
    return <Login onLogin={() => setIsLoggedIn(true)} />;
  }

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100">
      <NavBar current={view} onChange={setView} onLogout={() => setIsLoggedIn(false)} />
      <main className="p-6 max-w-7xl mx-auto">
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
      </main>
    </div>
  );
}
export default App;
