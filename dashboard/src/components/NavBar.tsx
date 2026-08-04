function NavBar({ current, onChange, onLogout }: { current: string; onChange: (v: string) => void; onLogout: () => void }) {
  const tabs = ['live', 'market', 'predictions', 'strategies', 'risk', 'reasoning', 'cycle', 'approvals', 'experiments', 'replay', 'backtest'];
  return (
    <nav className="bg-gray-900 p-4 flex gap-4 items-center justify-between border-b border-gray-800">
      <div className="flex gap-4">
        {tabs.map(tab => (
          <button
            key={tab}
            onClick={() => onChange(tab)}
            className={`px-4 py-2 rounded capitalize ${current === tab ? 'bg-indigo-600' : 'hover:bg-gray-800'}`}
          >
            {tab}
          </button>
        ))}
      </div>
      <button
        onClick={onLogout}
        className="px-4 py-2 bg-red-700 hover:bg-red-600 rounded"
      >
        Logout
      </button>
    </nav>
  );
}
export default NavBar;
