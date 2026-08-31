import { useEffect, useState } from "react";
import { authHeaders } from "../api/auth";
import { Button, Card, PageHeader, Badge, EmptyState, ErrorNote, Spinner } from "../components/ui";

// FIL Faz D — kullanıcı isteği (2026-08-31): "geçmiş benzer piyasa
// durumlarını eşleştiren" bir analiz — ajan-kombinasyonu × market_regime
// × yön üçlüsü için gerçek geçmiş kararlarda ne olduğunu gösterir.
// analytics/agent_combination_reliability.py'nin AYNI istatistiksel
// korumalarını (FDR + embargo'lu temporal-split OOS + min örneklem +
// örtüşme-düzeltmeli effective_sample_size) kullanıyor — SADECE ölçüm/
// analiz, karar hattına bağlı DEĞİL, hiçbir ajan ağırlığı/gate otomatik
// değişmiyor.
type Analog = {
  domains: string[];
  market_regime: string;
  direction: string;
  combination_size: number;
  sample_size: number;
  effective_sample_size: number;
  win_rate: number;
  win_rate_ci: { low: number; high: number; confidence_level: number };
  win_rate_delta_vs_baseline: number;
  fdr_significant: boolean;
  max_shared_trade_overlap_pct: number;
  distinct_days: number | null;
  oos_survival: boolean | null;
  gate_eligible: boolean;
};

type AnalogResult = {
  analogs: Analog[];
  baseline_win_rate: number | null;
  baseline_sample_size: number;
  n_trades: number;
};

export default function HistoricalAnalogs() {
  const [result, setResult] = useState<AnalogResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [onlyGateEligible, setOnlyGateEligible] = useState(false);
  // Faz 394 — kullanıcı isteği ("tam mimari değişim"): AgentCombinationReliability.tsx'in
  // Force-Open kartıyla AYNI desen (Settings'e DEĞİL, bkz. proje hafızası "settings placement: contextual").
  const [settings, setSettings] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    setError(null);
    Promise.all([
      fetch("/api/v1/historical-analogs/", { headers: authHeaders() }).then((r) => r.json()),
      fetch("/api/v1/settings/", { headers: authHeaders() }).then((r) => r.json()),
    ])
      .then(([data, settingsData]) => {
        setResult(data.result || null);
        setSettings(settingsData.settings || {});
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const save = (key: string, value: string) => {
    setSaving(key);
    setError(null);
    fetch(`/api/v1/settings/${key}?value=${encodeURIComponent(value)}`, {
      method: "POST",
      headers: authHeaders(),
    })
      .then(async (r) => {
        if (!r.ok) {
          const body = await r.json().catch(() => ({}));
          throw new Error(body.detail || `${r.status}`);
        }
        setSettings((s) => ({ ...s, [key]: value }));
      })
      .catch((e) => setError(`${key}: ${e.message || e}`))
      .finally(() => setSaving(null));
  };

  const overrideEnabled = settings.historical_analog_override_enabled === "true";

  const analogs = (result?.analogs || []).filter((a) => !onlyGateEligible || a.gate_eligible);

  return (
    <div>
      <PageHeader
        title="Tarihsel Analog Motoru"
        description={
          `"Bu ajan kombinasyonu + bu rejimde daha önce ne olmuş" sorusuna gerçek kapanmış kararlarla cevap. ` +
          `Ajan Kombinasyonu Güvenilirliği'nin AYNI istatistiksel korumaları (FDR + zamanla-tekrar/OOS + ` +
          `örtüşme-düzeltmeli örneklem) — üçüncü eksen olarak piyasa rejimi eklenmiş hâli.`
        }
      />

      {error && <ErrorNote>{error}</ErrorNote>}

      {/* Faz 394 — kullanıcı isteği (2026-09-01): "tam mimari değişim" —
          teknik ajanın yalnız kötü, belirli ortaklarla eşlikte çok iyi
          olduğu bulgusu üzerine, gate_eligible bir analog eşleştiğinde
          artık council'in ASIL confidence hesabının (belief.strength)
          YERİNE geçebiliyor (kenarda bir gate değil). Varsayılan KAPALI. */}
      <Card className="mb-6">
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <div>
            <h3 className="text-sm font-semibold text-ink mb-1">Confidence Override</h3>
            <p className="text-xs text-ink-soft">
              Açıksa: bir kararda "kapı uygun" bir analog eşleşirse (ajan kombinasyonu + rejim + yön), council'in
              cluster/crowding/coverage skorlamasından gelen confidence'ı (belief.strength) GERÇEK ampirik kazanma
              oranı ile DEĞİŞTİRİR — eşleşme yoksa (bugün kararların ezici çoğunluğu) hiçbir şey değişmez. Sadece
              YÜKSELTİR, asla düşürmez. Kalibrasyon/opportunity-quality/InnerCritic gibi son güvenlik katmanları hâlâ
              devrede.
            </p>
          </div>
          <Button
            variant={overrideEnabled ? "danger" : "secondary"}
            disabled={saving === "historical_analog_override_enabled"}
            onClick={() => save("historical_analog_override_enabled", overrideEnabled ? "false" : "true")}
            className="!px-3 !py-1.5 text-xs shrink-0"
          >
            {overrideEnabled ? "Override'ı Kapat" : "Override'ı Aç"}
          </Button>
        </div>
      </Card>

      <Card className="mb-6">
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <div>
            <h3 className="text-sm font-semibold text-ink mb-1">Canlı ölçüm</h3>
            <p className="text-xs text-ink-soft">
              Her sorguda gerçek kapanmış kararlardan taze hesaplanır (pump-fade hariç). "Kapı uygun" üçünün
              (FDR-anlamlı + OOS'ta tekrarlanmış + yeterli bağımsız örneklem) birlikte sağlandığı tek bakışta
              okunabilir bayrak — hiçbir karara otomatik bağlanmıyor, sadece işaret.
            </p>
          </div>
          <label className="flex items-center gap-2 text-xs text-ink-soft shrink-0">
            <input
              type="checkbox"
              checked={onlyGateEligible}
              onChange={(e) => setOnlyGateEligible(e.target.checked)}
            />
            Sadece kapı uygun olanlar
          </label>
        </div>
      </Card>

      <Card>
        {loading ? (
          <Spinner />
        ) : !result || analogs.length === 0 ? (
          <EmptyState
            label={`Henüz yeterli veri yok (${result?.n_trades ?? 0} işlem, min. 20 örneklem/hücre gerekiyor).`}
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-left text-ink-faint border-b border-line-soft">
                  <th className="py-2 pr-4">Ajan kombinasyonu</th>
                  <th className="py-2 pr-4">Rejim</th>
                  <th className="py-2 pr-4">Yön</th>
                  <th className="py-2 pr-4">Kazanma oranı</th>
                  <th className="py-2 pr-4">Baseline'a fark</th>
                  <th className="py-2 pr-4">Örneklem</th>
                  <th className="py-2 pr-4">Bağımsız N</th>
                  <th className="py-2 pr-4">Gün sayısı</th>
                  <th className="py-2 pr-4">Zamanla tekrar</th>
                  <th className="py-2 pr-4">Kapı uygun</th>
                </tr>
              </thead>
              <tbody>
                {analogs.map((a, i) => (
                  <tr key={i} className="border-b border-line-soft/50">
                    <td className="py-2 pr-4 font-mono text-ink">{a.domains.join(" + ")}</td>
                    <td className="py-2 pr-4 text-ink-soft">{a.market_regime}</td>
                    <td className="py-2 pr-4 text-ink-soft">{a.direction}</td>
                    <td className="py-2 pr-4">
                      <Badge tone={a.win_rate_delta_vs_baseline >= 0 ? "rise" : "fall"}>
                        {(a.win_rate * 100).toFixed(1)}%
                      </Badge>
                    </td>
                    <td className="py-2 pr-4 text-ink-soft">
                      {a.win_rate_delta_vs_baseline >= 0 ? "+" : ""}
                      {(a.win_rate_delta_vs_baseline * 100).toFixed(1)}pp
                    </td>
                    <td className="py-2 pr-4 text-ink-soft">{a.sample_size}</td>
                    <td className="py-2 pr-4 text-ink-soft">{a.effective_sample_size}</td>
                    <td className="py-2 pr-4 text-ink-soft">{a.distinct_days ?? "—"}</td>
                    <td className="py-2 pr-4 text-ink-soft">
                      {a.oos_survival === null ? "—" : a.oos_survival ? "evet" : "hayır"}
                    </td>
                    <td className="py-2 pr-4">
                      {a.gate_eligible ? <Badge tone="accent">uygun</Badge> : <span className="text-ink-faint">—</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
