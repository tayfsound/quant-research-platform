import { useEffect, useState } from "react";
import { authHeaders } from "../api/auth";
import { Card, PageHeader, Button, ErrorNote, EmptyState } from "../components/ui";

// Faz 268ai — kullanıcı isteği: Predictions sayfası eskiden manuel "Run
// Cycle" ile Direction/Risk Verdict/Simulated PnL gösteriyordu. Kullanıcı
// bulgusu: risk kontrolü (cooldown vb.) council'den ÖNCE çalıştığı için
// manuel tetikleme çoğu zaman council'i hiç çalıştırmadan reddediliyor —
// "isabet" ölçmek için faydasız (gerçek isabet Performance/Transactions'
// taki GERÇEK kapanmış işlemlerden ölçülüyor). Features ise farklı: ctx.
// market.features risk kontrolünden ÖNCE hesaplanıyor, cooldown'da bile
// dolu geliyor (doğrulandı: 27 gerçek sinyal) — o yüzden SADECE bu kısım
// tutuldu, Direction/Risk Verdict/Simulated PnL kartları tamamen kaldırıldı.
export default function Predictions() {
  const [features, setFeatures] = useState<Record<string, unknown> | null>(null);
  const [resultSymbol, setResultSymbol] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [watchlist, setWatchlist] = useState<string[]>([]);
  const [symbol, setSymbol] = useState("");

  useEffect(() => {
    fetch("/api/v1/settings/", { headers: authHeaders() })
      .then((r) => r.json())
      .then((data) => {
        const raw = data.settings?.watchlist || "";
        const list = raw.split(",").map((s: string) => s.trim()).filter(Boolean);
        setWatchlist(list);
        if (list.length > 0) setSymbol(list[0]);
      })
      .catch(() => setWatchlist([]));
  }, []);

  const fetchFeatures = () => {
    setLoading(true);
    setError(null);
    fetch("/api/v1/orchestrator/cycle", {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ seed: Math.floor(Math.random() * 100000), symbol: symbol || undefined }),
    })
      .then(async (r) => {
        const data = await r.json();
        if (!r.ok) throw new Error(data.detail || `HTTP ${r.status}`);
        setFeatures(data.features || {});
        setResultSymbol(data.symbol || symbol);
      })
      .catch((e) => setError(String(e.message || e)))
      .finally(() => setLoading(false));
  };

  return (
    <div>
      <PageHeader
        title="Predictions"
        description="Sembolün şu anki gerçek teknik/onchain sinyal değerleri — risk/cooldown kontrolünden bağımsız, her zaman güncel."
        action={
          <div className="flex items-center gap-2">
            <select
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              className="px-3 py-2 rounded-lg bg-canvas-soft border border-line text-sm text-ink focus:outline-none focus:ring-2 focus:ring-accent/30 focus:border-accent"
            >
              {watchlist.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
            <Button onClick={fetchFeatures} disabled={loading}>
              {loading ? "Getiriliyor…" : "Sinyalleri Getir"}
            </Button>
          </div>
        }
      />

      {error && <ErrorNote>{error}</ErrorNote>}

      {!features && !error && (
        <EmptyState label="Henüz getirilmedi — güncel sinyalleri görmek için “Sinyalleri Getir”e basın." />
      )}

      {features && (
        <Card>
          <p className="text-xs text-ink-faint uppercase tracking-wide">Features — {resultSymbol}</p>
          <div className="text-xs text-ink-soft mt-3 space-y-1.5">
            {Object.entries(features).map(([k, v]) => (
              <div key={k} className="flex justify-between gap-2">
                <span className="capitalize shrink-0">{k}</span>
                <span className="font-mono text-right break-all min-w-0">
                  {typeof v === "number" ? v.toFixed(4) : String(v)}
                </span>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}
