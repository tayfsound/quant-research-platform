const GROUPS: { label: string; items: { key: string; label: string }[] }[] = [
  {
    label: "Live",
    items: [
      { key: "dashboard", label: "Dashboard" },
      { key: "transactions", label: "Transactions" },
      { key: "performance", label: "Performance" },
      { key: "cycle", label: "Latest Cycle" },
      { key: "tokens", label: "Tokens" },
      { key: "market", label: "Market" },
      { key: "predictions", label: "Predictions" },
    ],
  },
  {
    label: "Research",
    items: [
      { key: "strategies", label: "Agents" },
      { key: "backtest", label: "Backtests" },
      { key: "replay", label: "Replay" },
      { key: "explain", label: "Explain" },
    ],
  },
  {
    label: "Risk & Ops",
    items: [
      { key: "risk", label: "Risk" },
      { key: "settings", label: "Settings" },
      { key: "approvals", label: "Approvals" },
      { key: "workspace", label: "Workspace" },
    ],
  },
];

function Sidebar({ current, onChange, onLogout }: { current: string; onChange: (v: string) => void; onLogout: () => void }) {
  return (
    <nav className="w-64 shrink-0 h-screen sticky top-0 flex flex-col p-4">
      <div className="flex-1 flex flex-col bg-surface border border-line rounded-xl shadow-layer-2 overflow-hidden">
        <div className="px-5 py-5 border-b border-line-soft">
          <div className="flex items-center gap-2">
            <div className="w-2.5 h-2.5 rounded-full bg-accent" />
            <div className="font-semibold text-sm tracking-tight text-ink">AI Quant Research</div>
          </div>
          <div className="text-[11px] text-ink-faint mt-0.5 pl-4.5">Cognitive Core</div>
        </div>

        <div className="flex-1 overflow-y-auto py-3 px-3">
          {GROUPS.map((group) => (
            <div key={group.label} className="mb-4">
              <div className="px-2 py-1 text-[10px] uppercase tracking-wider text-ink-faint font-semibold">
                {group.label}
              </div>
              <div className="flex flex-col gap-0.5 mt-1">
                {group.items.map((item) => {
                  const active = current === item.key;
                  return (
                    <button
                      key={item.key}
                      onClick={() => onChange(item.key)}
                      className={`text-left px-3 py-2 text-sm rounded-lg font-medium ${
                        active
                          ? "bg-accent text-white shadow-layer-1"
                          : "text-ink-soft hover:bg-canvas-soft hover:text-ink"
                      }`}
                    >
                      {item.label}
                    </button>
                  );
                })}
              </div>
            </div>
          ))}
        </div>

        <div className="p-3 border-t border-line-soft">
          <button
            onClick={onLogout}
            className="w-full px-3 py-2 rounded-lg text-sm font-medium text-ink-soft hover:bg-fall-soft hover:text-fall"
          >
            Log out
          </button>
        </div>
      </div>
    </nav>
  );
}
export default Sidebar;
