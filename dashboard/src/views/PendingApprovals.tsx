import { useEffect, useState } from "react";
import { authHeaders } from "../api/auth";
import { Card, PageHeader, Button, Badge, ErrorNote, EmptyState } from "../components/ui";

type Approval = {
  id: string;
  timestamp: string | null;
  proposed: Record<string, number>;
  previous: Record<string, number>;
  max_delta: number;
  regime: string | null;
  status: string;
};

// Faz 224: kullanıcı bulgusu — "Approval a gelen onay sorularının formatı
// çok dağınık kod gibi görünüyor... yatay scrolling felan yapmadan
// onaylayamıyorum çok özensiz." Eskiden JSON.stringify(a.proposed) tek
// satırlık font-mono metin olarak basılıyordu — hem önceki değeri hiç
// göstermiyordu hem de yatay taşıyordu. Artık her ajan domain'i için
// önceki/yeni/değişim ayrı satırlarda, en büyük değişiklik en üstte.
function WeightDiffRows({ proposed, previous }: { proposed: Record<string, number>; previous: Record<string, number> }) {
  const domains = Array.from(new Set([...Object.keys(previous), ...Object.keys(proposed)]));
  const rows = domains
    .map((domain) => {
      // Faz 268-sonrası kullanıcı bulgusu: bir ajanın bu rejimde HİÇ
      // önceki ağırlığı yoksa (0.000 değil, tamamen kayıtsız), "0.000 →
      // X" olarak göstermek yanıltıcı — bu bir "büyük değişiklik" değil,
      // ilk kez değer alması (cold start). isNew ile ayırt ediyoruz;
      // delta sıralaması hâlâ gerçek sayısal farka göre ama satırda
      // görünür şekilde işaretleniyor.
      const isNew = !(domain in previous);
      const before = previous[domain] ?? 0;
      const after = proposed[domain] ?? 0;
      return { domain, before, after, delta: after - before, isNew };
    })
    .sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta));

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-xs text-ink-faint uppercase tracking-wide border-b border-line-soft">
            <th className="py-1.5 pr-4 font-medium">Ajan</th>
            <th className="py-1.5 pr-4 font-medium">Önceki</th>
            <th className="py-1.5 pr-4 font-medium">Yeni</th>
            <th className="py-1.5 pr-4 font-medium">Değişim</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.domain} className="border-b border-line-soft last:border-0">
              <td className="py-1.5 pr-4 text-ink font-medium">{r.domain}</td>
              <td className="py-1.5 pr-4 text-ink-soft font-mono">
                {r.isNew ? "— (yeni)" : r.before.toFixed(3)}
              </td>
              <td className="py-1.5 pr-4 text-ink font-mono">{r.after.toFixed(3)}</td>
              <td className={`py-1.5 pr-4 font-mono ${r.isNew ? "text-ink-faint" : r.delta > 0 ? "text-rise" : r.delta < 0 ? "text-fall" : "text-ink-faint"}`}>
                {r.isNew ? "ilk değer" : `${r.delta > 0 ? "+" : ""}${r.delta.toFixed(3)}`}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// Faz 366 — kullanıcı isteği: "ürettiği strateji insan onayına sunulur
// böyle bir yapı ayarlamıştık." strategy_hypothesis_scanner.py'nin
// (Faz 346) bulduğu (strateji × rejim) adayları — WeightApproval ile
// AYNI propose→pending→approve/reject döngüsü, ayrı bir bekleyen-onay
// tipi.
type StrategyGateCandidate = {
  id: string;
  timestamp: string | null;
  strategy: string;
  market_regime: string;
  sample_size: number;
  win_rate: number;
  rest_win_rate: number;
  delta_vs_rest: number;
  p_value: number;
  replicated_out_of_sample: boolean | null;
  status: string;
};

function StrategyGateCard({
  candidate, busy, onDecide,
}: {
  candidate: StrategyGateCandidate;
  busy: boolean;
  onDecide: (id: string, action: "approve" | "reject") => void;
}) {
  return (
    <Card>
      <div className="flex items-start justify-between gap-4 mb-3">
        <div>
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-ink font-medium">{candidate.strategy}</span>
            <Badge tone="accent">rejim: {candidate.market_regime}</Badge>
            {candidate.replicated_out_of_sample && (
              <Badge tone="rise">out-of-sample'da tekrarlandı</Badge>
            )}
          </div>
          {candidate.timestamp && (
            <p className="text-xs text-ink-faint mt-1">{new Date(candidate.timestamp).toLocaleString()}</p>
          )}
        </div>
        <div className="flex gap-2 shrink-0">
          <Button variant="danger" disabled={busy} onClick={() => onDecide(candidate.id, "reject")}>
            Reddet
          </Button>
          <Button disabled={busy} onClick={() => onDecide(candidate.id, "approve")}>
            Onayla (bu rejimde bu stratejiyi engelle)
          </Button>
        </div>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
        <div>
          <p className="text-xs text-ink-faint">Bu hücrede win rate</p>
          <p className="text-fall font-mono">{(candidate.win_rate * 100).toFixed(1)}%</p>
        </div>
        <div>
          <p className="text-xs text-ink-faint">Geri kalanında win rate</p>
          <p className="text-rise font-mono">{(candidate.rest_win_rate * 100).toFixed(1)}%</p>
        </div>
        <div>
          <p className="text-xs text-ink-faint">Fark</p>
          <p className="font-mono">{(candidate.delta_vs_rest * 100).toFixed(1)} puan</p>
        </div>
        <div>
          <p className="text-xs text-ink-faint">Örneklem / p-değeri</p>
          <p className="font-mono">n={candidate.sample_size}, p={candidate.p_value.toFixed(4)}</p>
        </div>
      </div>
    </Card>
  );
}

export default function PendingApprovals() {
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [strategyGates, setStrategyGates] = useState<StrategyGateCandidate[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = () => {
    fetch("/api/v1/weights/pending?limit=10")
      .then((r) => r.json())
      .then((data) => setApprovals(data.pending || []));
    fetch("/api/v1/strategy-gates/pending?limit=10")
      .then((r) => r.json())
      .then((data) => setStrategyGates(data.pending || []));
  };

  useEffect(() => {
    load();
    const interval = setInterval(load, 15000);
    return () => clearInterval(interval);
  }, []);

  const decide = (id: string, action: "approve" | "reject") => {
    setError(null);
    setBusyId(id);
    // OPERATOR+ rolü gerektirir — ağırlık onayı sistemdeki en kritik
    // insan-müdahale noktalarından biri.
    fetch(`/api/v1/weights/${id}/${action}`, { method: "POST", headers: authHeaders() })
      .then(async (r) => {
        if (!r.ok) {
          const data = await r.json().catch(() => ({}));
          throw new Error(data.detail || `HTTP ${r.status}`);
        }
        setApprovals((prev) => prev.filter((a) => a.id !== id));
      })
      .catch((e) => setError(String(e.message || e)))
      .finally(() => setBusyId(null));
  };

  const decideStrategyGate = (id: string, action: "approve" | "reject") => {
    setError(null);
    setBusyId(id);
    fetch(`/api/v1/strategy-gates/${id}/${action}`, { method: "POST", headers: authHeaders() })
      .then(async (r) => {
        if (!r.ok) {
          const data = await r.json().catch(() => ({}));
          throw new Error(data.detail || `HTTP ${r.status}`);
        }
        setStrategyGates((prev) => prev.filter((a) => a.id !== id));
      })
      .catch((e) => setError(String(e.message || e)))
      .finally(() => setBusyId(null));
  };

  return (
    <div>
      <PageHeader
        title="Pending Approvals"
        description="Ajan ağırlık güncellemeleri ve strateji kapı adayları — büyük bir değişiklik ya da yeni bir engelleme önerildiğinde otomatik uygulanmaz, insan onayı bekler."
      />
      {error && <ErrorNote>{error}</ErrorNote>}

      <div className="mb-6">
        <h2 className="text-sm font-semibold text-ink mb-3">Ajan Ağırlıkları</h2>
        {approvals.length === 0 ? (
          <EmptyState label="Bekleyen ağırlık onayı yok." />
        ) : (
          <div className="space-y-4">
            {approvals.map((a) => (
              <Card key={a.id}>
                <div className="flex items-start justify-between gap-4 mb-3">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-ink font-medium font-mono text-xs">{a.id.slice(0, 8)}…</span>
                      {/* Faz 268-sonrası kullanıcı bulgusu: bu SAYI bir tavan
                          DEĞİL — propose_weights() önerilen değeri buna göre
                          hiç kırpmıyor, sadece bunu AŞARSA onay isteniyor.
                          Eski etiket ("izin verilen max değişim") tam tersini
                          ima ediyordu; aşağıdaki tablodaki değişim bundan
                          çok daha büyük olabilir. */}
                      <Badge tone="neutral">onay eşiği (bunun üstünde olduğu için soruluyor): ±{a.max_delta.toFixed(2)}</Badge>
                      {/* Faz 268b — Regime-Aware Learning: bu öneri global mi
                          (rejimden bağımsız, tüm geçmiş) yoksa belirli bir
                          piyasa rejimi için mi (ör. bullish_high) — insan
                          onaylayıcının NE'yi onayladığını bilmesi lazım. */}
                      <Badge tone={a.regime ? "accent" : "neutral"}>
                        {a.regime ? `rejim: ${a.regime}` : "global"}
                      </Badge>
                    </div>
                    {a.timestamp && (
                      <p className="text-xs text-ink-faint mt-1">{new Date(a.timestamp).toLocaleString()}</p>
                    )}
                  </div>
                  <div className="flex gap-2 shrink-0">
                    <Button
                      variant="danger"
                      disabled={busyId === a.id}
                      onClick={() => decide(a.id, "reject")}
                    >
                      Reddet
                    </Button>
                    <Button disabled={busyId === a.id} onClick={() => decide(a.id, "approve")}>
                      Onayla
                    </Button>
                  </div>
                </div>
                <WeightDiffRows proposed={a.proposed} previous={a.previous} />
              </Card>
            ))}
          </div>
        )}
      </div>

      <div>
        <h2 className="text-sm font-semibold text-ink mb-3">Strateji Kapı Adayları</h2>
        {strategyGates.length === 0 ? (
          <EmptyState label="Bekleyen strateji kapı adayı yok." />
        ) : (
          <div className="space-y-4">
            {strategyGates.map((c) => (
              <StrategyGateCard
                key={c.id}
                candidate={c}
                busy={busyId === c.id}
                onDecide={decideStrategyGate}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
