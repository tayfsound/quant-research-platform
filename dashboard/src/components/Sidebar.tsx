// Faz 181 (minimal): replaces the single-row, 13-tab NavBar (which would
// wrap/overflow awkwardly) with a grouped sidebar — closer to the
// terminal-style layout the roadmap wants, without the scope of a full
// custom UI framework rebuild.
const GROUPS: { label: string; items: string[] }[] = [
  { label: 'Live', items: ['live', 'cycle', 'market', 'predictions'] },
  { label: 'Research', items: ['strategies', 'reasoning', 'backtest', 'replay', 'experiments', 'explain'] },
  { label: 'Risk & Ops', items: ['risk', 'approvals', 'workspace'] },
];

function Sidebar({ current, onChange, onLogout }: { current: string; onChange: (v: string) => void; onLogout: () => void }) {
  return (
    <nav className="w-56 shrink-0 bg-gray-900 border-r border-gray-800 flex flex-col h-screen sticky top-0">
      <div className="px-4 py-4 border-b border-gray-800">
        <div className="font-bold text-sm tracking-wide">AI QUANT RESEARCH</div>
      </div>
      <div className="flex-1 overflow-y-auto py-2">
        {GROUPS.map((group) => (
          <div key={group.label} className="mb-3">
            <div className="px-4 py-1 text-[10px] uppercase tracking-wider text-gray-500">
              {group.label}
            </div>
            {group.items.map((item) => (
              <button
                key={item}
                onClick={() => onChange(item)}
                className={`w-full text-left px-4 py-1.5 text-sm capitalize ${
                  current === item ? 'bg-indigo-600 text-white' : 'text-gray-300 hover:bg-gray-800'
                }`}
              >
                {item}
              </button>
            ))}
          </div>
        ))}
      </div>
      <div className="p-3 border-t border-gray-800">
        <button
          onClick={onLogout}
          className="w-full px-3 py-2 bg-red-700 hover:bg-red-600 rounded text-sm"
        >
          Logout
        </button>
      </div>
    </nav>
  );
}
export default Sidebar;
