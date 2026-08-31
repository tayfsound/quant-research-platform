import { useState } from "react";

const GROUPS: { label: string; items: { key: string; label: string }[] }[] = [
  {
    label: "Live",
    items: [
      { key: "dashboard", label: "Dashboard" },
      { key: "transactions", label: "Transactions" },
      { key: "tokens", label: "Tokens" },
      { key: "market", label: "Market" },
      { key: "predictions", label: "Predictions" },
    ],
  },
  {
    label: "Research",
    items: [
      { key: "research-summary", label: "Genel Özet" },
      { key: "strategies", label: "Agents" },
      { key: "feature-ic", label: "Feature IC" },
      { key: "self-model", label: "Self-Model" },
      { key: "causal-inference", label: "Causal Inference" },
      { key: "collective-intelligence", label: "Collective Intelligence" },
      { key: "mae-mfe-confidence", label: "MAE/MFE Güven Aralığı" },
      { key: "meta-learning-effectiveness", label: "Meta-Learning Effectiveness" },
      { key: "market-world-model", label: "Risk Simülatörü" },
      { key: "direction-prediction-v2", label: "Direction Prediction v2" },
      { key: "opportunity-quality", label: "Opportunity Quality" },
      { key: "agent-ablation", label: "Agent Ablation" },
      { key: "tp-sl-confluence", label: "TP/SL Confluence" },
      { key: "agent-combination-reliability", label: "Ajan Kombinasyonu Güvenilirliği" },
      { key: "historical-analogs", label: "Tarihsel Analog Motoru" },
      { key: "strategy-regime-compatibility", label: "Strateji × Rejim Uyumu" },
      { key: "strategy-hypothesis-scanner", label: "Strateji Hipotez Tarayıcı" },
    ],
  },
  {
    label: "Risk & Ops",
    items: [
      { key: "settings", label: "Settings" },
      { key: "approvals", label: "Approvals" },
      { key: "workspace", label: "Workspace" },
    ],
  },
];

// Kullanıcı isteği: tabloları incelerken menü ekranda yer kaplamasın,
// gizlenebilir olsun — küçük bir sekme/buton ile aç/kapa VEYA fare sol
// kenara yaklaşınca kendiliğinden açılıp uzaklaşınca kapanabilsin (ikisi
// birlikte). `collapsed` App.tsx'te localStorage'a yazılıp kalıcı tutulan
// "sabitlenmiş" durumu temsil ediyor; `hoverOpen` ise SADECE collapsed
// haldeyken sol kenar hover'ıyla açılan GEÇİCİ görünürlük — sabit durumu
// hiç değiştirmiyor, fare çekilince tekrar kapanıyor.
function Sidebar({
  current,
  onChange,
  onLogout,
  collapsed,
  onToggleCollapsed,
}: {
  current: string;
  onChange: (v: string) => void;
  onLogout: () => void;
  collapsed: boolean;
  onToggleCollapsed: () => void;
}) {
  const [hoverOpen, setHoverOpen] = useState(false);
  const visible = !collapsed || hoverOpen;

  return (
    <>
      {collapsed && (
        // Sol kenara ~1cm'lik görünmez algılama şeridi — üzerine gelince
        // menü geçici olarak açılır.
        <div
          className="fixed top-0 left-0 h-screen w-4 z-40"
          onMouseEnter={() => setHoverOpen(true)}
        />
      )}

      <nav
        onMouseLeave={() => {
          if (collapsed) setHoverOpen(false);
        }}
        className={`w-64 shrink-0 h-screen flex flex-col p-4 z-40 transition-transform duration-200 ease-out ${
          collapsed
            ? `fixed top-0 left-0 ${visible ? "translate-x-0" : "-translate-x-[110%]"}`
            : "sticky top-0 translate-x-0"
        }`}
      >
        <div className="flex-1 flex flex-col glass-panel border border-line rounded-xl shadow-layer-2 overflow-hidden">
          <div className="px-5 py-5 border-b border-line-soft flex items-start justify-between gap-2">
            <div>
              <div className="flex items-center gap-2">
                <div className="w-2.5 h-2.5 rounded-full bg-accent" />
                <div className="font-semibold text-sm tracking-tight text-ink">AI Quant Research</div>
              </div>
              <div className="text-[11px] text-ink-faint mt-0.5 pl-4.5">Cognitive Core</div>
            </div>
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

      {/* Kullanıcı isteği (2026-08-28, ekran görüntüsüyle doğrulandı):
          gizle/göster için TEK buton — eski "göster" sekmesinin (sol
          kenar, dikey orta, dar dikdörtgen/pill) AYNI görünümü/konumu,
          artık her iki durumda da (nav'ın translate'inden bağımsız,
          sabit ekran konumunda) görünür — sadece ok yönü değişiyor. */}
      {/* Kullanıcı isteği: menü açıldığında buton da onunla birlikte sağa
          kayıp nav'ın (w-64=256px) sağ kenarına aynı hizada otursun —
          nav'ın kendi geçişiyle (duration-200 ease-out) AYNI zamanlama. */}
      <button
        onClick={onToggleCollapsed}
        title={visible ? "Menüyü gizle" : "Menüyü göster"}
        aria-label={visible ? "Menüyü gizle" : "Menüyü göster"}
        className={`fixed top-1/2 -translate-y-1/2 z-50 w-5 h-14 rounded-r-full flex items-center justify-center bg-accent text-white shadow-layer-2 opacity-60 hover:opacity-100 transition-[left,opacity] duration-200 ease-out ${
          // nav w-64(256px) kendi p-4(16px) iç boşluğuna sahip — görünen
          // cam panelin GERÇEK sağ kenarı 256-16=240px'te (left-60),
          // 256px'te (left-64) DEĞİL. Kullanıcı bulgusu: ilk denemede
          // nav'ın dış kutusunu baz almıştım, panelle buton arasında
          // görünür bir boşluk kalmıştı.
          visible ? "left-60" : "left-0"
        }`}
      >
        {visible ? "‹" : "›"}
      </button>
    </>
  );
}
export default Sidebar;
