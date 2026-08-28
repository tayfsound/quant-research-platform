import { useEffect, useState } from "react";
import { authHeaders } from "../api/auth";
import { Button, Card, PageHeader, Badge, EmptyState, ErrorNote, Spinner } from "../components/ui";

// Faz 331 — kullanıcı isteği (harici bir AI incelemesinin önerdiği,
// defalarca gündeme gelip ertelenen bir madde): Opportunity Quality
// (analytics/opportunity_quality.py) council'de KAÇ ajanın anlaştığını
// win_rate ile ilişkilendiriyor — bu sayfa HANGİ ajan GRUPLARININ
// birlikte anlaştığını ilişkilendiriyor. Sadece ölçüm/izleme — hiçbir
// ajan ağırlığını/karar mantığını otomatik değiştirmiyor.
//
// Faz 367-devam — kullanıcı isteği: sabit "ikili" yerine artık 2/3/4'lü
// gruplar AYNI ANDA test ediliyor (örneklem arttıkça büyük gruplar
// kendiliğinden tabloya girer) — domain_a/domain_b yerine `domains`
// (değişken uzunlukta) + `combination_size`. Kullanıcı bulgusu: aynı
// domaini paylaşan gruplar genelde AYNI işlemleri sayıyor (bir 3'lü,
// onu kapsayan bir 2'liyle neredeyse tamamen örtüşebilir) — bu örtüşme
// artık `max_shared_trade_overlap_pct` ile görünür, "bağımsız bulgu"
// yanılgısına karşı dürüst bir uyarı.
type CombinationPair = {
  domains: string[];
  combination_size: number;
  sample_size: number;
  win_rate: number;
  win_rate_ci: { low: number; high: number; confidence_level: number };
  win_rate_delta_vs_baseline: number;
  fdr_significant: boolean;
  max_shared_trade_overlap_pct: number;
  max_shared_trade_overlap_with: string[] | null;
  distinct_days: number | null;
};

type CombinationResult = {
  pairs: CombinationPair[];
  baseline_win_rate: number | null;
  baseline_sample_size: number;
  n_trades: number;
};

type CombinationReport = {
  id: string;
  created_at: string;
  result: CombinationResult;
};

export default function AgentCombinationReliability() {
  const [live, setLive] = useState<CombinationResult | null>(null);
  const [reports, setReports] = useState<CombinationReport[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // Kullanıcı isteği (2026-08-28): "kapı nereden açılıyor, UI'da buton
  // var mı?" — Settings'e DEĞİL, burada (bkz. proje hafızası "settings
  // placement: contextual"), Dashboard.tsx'teki generic save() deseniyle
  // AYNI.
  const [settings, setSettings] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState<string | null>(null);
  const [minWinRateInput, setMinWinRateInput] = useState("");

  const load = () => {
    setLoading(true);
    setError(null);
    Promise.all([
      fetch("/api/v1/agent-combination-reliability/", { headers: authHeaders() }).then((r) => r.json()),
      fetch("/api/v1/agent-combination-reliability/reports?limit=20", { headers: authHeaders() }).then((r) => r.json()),
      fetch("/api/v1/settings/", { headers: authHeaders() }).then((r) => r.json()),
    ])
      .then(([liveData, history, settingsData]) => {
        setLive(liveData.result || null);
        setReports(history.reports || []);
        setSettings(settingsData.settings || {});
        setMinWinRateInput(settingsData.settings?.agent_combination_gate_min_win_rate ?? "0.74");
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

  const gateEnabled = settings.agent_combination_gate_enabled === "true";

  return (
    <div>
      <PageHeader
        title="Ajan Kombinasyonu Güvenilirliği"
        description="Opportunity Quality KAÇ ajanın anlaştığını ölçüyor — bu sayfa HANGİ ajan gruplarının (2/3/4'lü, örneklem arttıkça kendiliğinden büyür) birlikte anlaştığını ölçüyor. Tüm gruplar aynı anda test edildiği için çoklu-test düzeltmesi (Benjamini-Hochberg FDR) uygulanıyor — sadece ölçüm/izleme, hiçbir ajan ağırlığı otomatik değişmiyor."
      />

      {error && <ErrorNote>{error}</ErrorNote>}

      {/* Kullanıcı isteği (2026-08-28): karar mekanizmasına bağlanan
          kapının UI'dan açılıp kapatılabilmesi + eşiğin ayarlanabilmesi.
          Varsayılan KAPALI (fail-open, adım adım aktivasyon ilkesi). */}
      <Card className="mb-6">
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <div>
            <h3 className="text-sm font-semibold text-ink mb-1">Karar Kapısı</h3>
            <p className="text-xs text-ink-soft">
              Açıksa: bir kararda anlaşan ajan grubu, en son haftalık raporda bilinen (FDR'ı geçmiş, düşük
              örtüşmeli) düşük-güvenilirlikli bir grupla eşleşirse pozisyon açılmaz.
            </p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <input
              type="number"
              step="0.01"
              min="0"
              max="1"
              value={minWinRateInput}
              onChange={(e) => setMinWinRateInput(e.target.value)}
              onBlur={() => {
                if (minWinRateInput && minWinRateInput !== settings.agent_combination_gate_min_win_rate) {
                  save("agent_combination_gate_min_win_rate", minWinRateInput);
                }
              }}
              disabled={saving === "agent_combination_gate_min_win_rate"}
              className="w-20 px-2 py-1.5 rounded-lg text-xs font-mono border border-line bg-surface text-ink shadow-sm focus:outline-none focus:ring-2 focus:ring-accent/30 focus:border-accent"
              title="Eşik win_rate (0-1 arası, ör. 0.74)"
            />
            <Button
              variant={gateEnabled ? "danger" : "secondary"}
              disabled={saving === "agent_combination_gate_enabled"}
              onClick={() => save("agent_combination_gate_enabled", gateEnabled ? "false" : "true")}
              className="!px-3 !py-1.5 text-xs"
            >
              {gateEnabled ? "Kapıyı Kapat" : "Kapıyı Aç"}
            </Button>
          </div>
        </div>
      </Card>

      <Card className="mb-6">
        <h3 className="text-sm font-semibold text-ink mb-1">Canlı ölçüm</h3>
        <p className="text-xs text-ink-soft mb-3">
          Her sorguda gerçek kapanmış işlemlerden taze hesaplanır. Bir grup (2/3/4'lü), en az 20 gerçek işlemde
          birlikte nihai yönle aynı yönde oy vermişse listelenir, kazanma oranına göre en yüksekten en düşüğe
          sıralı. "Örtüşme" sütunu, grubun işlemlerinin ne kadarının AYNI zamanda başka (domain paylaşan) bir
          grupla da örtüştüğünü gösterir — yüksek örtüşme, bunun bağımsız bir bulgu değil, aynı işlemlerin
          tekrar sayımı olabileceği anlamına gelir. "Gün sayısı" grubun işlemlerinin kaç FARKLI takvim gününe
          yayıldığını gösterir — düşük gün sayısı (ör. tüm işlemler 1-2 günlük tek bir dar pencereden), düşük
          örtüşmeye sahip bir grup için bile "bağımsız kanıt" yerine dar bir rejim/olay artefaktı olabileceğine
          işaret eder.
        </p>

        {loading ? (
          <Spinner />
        ) : !live || live.pairs.length === 0 ? (
          <EmptyState label={`Henüz yeterli veri yok (${live?.n_trades ?? 0} işlem, min. 20 örneklem/grup gerekiyor).`} />
        ) : (
          <div className="overflow-x-auto">
            <p className="text-xs text-ink-faint mb-2">
              {live.n_trades} işlem incelendi, genel ortalama kazanma oranı{" "}
              <strong>%{((live.baseline_win_rate ?? 0) * 100).toFixed(1)}</strong> ({live.baseline_sample_size} işlem).{" "}
              {live.pairs.length} grup yeterli örnekleme sahip, bunlardan{" "}
              <strong>{live.pairs.filter((p) => p.fdr_significant).length}</strong> tanesi çoklu-test düzeltmesinden
              (FDR) sonra da anlamlı.
            </p>
            <table className="w-full text-xs">
              <thead>
                <tr className="text-left text-ink-faint border-b border-line-soft">
                  <th className="py-2 pr-4">Ajan grubu</th>
                  <th className="py-2 pr-4">Boyut</th>
                  <th className="py-2 pr-4">Kazanma oranı</th>
                  <th className="py-2 pr-4">Baseline'a göre fark</th>
                  <th className="py-2 pr-4">Örneklem</th>
                  <th className="py-2 pr-4">Örtüşme</th>
                  <th className="py-2 pr-4">Gün sayısı</th>
                  <th className="py-2 pr-4">FDR sonrası</th>
                </tr>
              </thead>
              <tbody>
                {live.pairs.map((p, i) => (
                  <tr key={`${p.domains.join("+")}-${i}`} className="border-b border-line-soft/50">
                    <td className="py-2 pr-4 font-mono text-ink">{p.domains.join(" + ")}</td>
                    <td className="py-2 pr-4 text-ink-soft">{p.combination_size}'li</td>
                    <td className="py-2 pr-4">
                      <Badge tone={p.win_rate >= 0.8 ? "rise" : "accent"}>%{(p.win_rate * 100).toFixed(1)}</Badge>
                    </td>
                    <td className={`py-2 pr-4 ${p.win_rate_delta_vs_baseline >= 0 ? "text-rise" : "text-fall"}`}>
                      {p.win_rate_delta_vs_baseline >= 0 ? "+" : ""}
                      {(p.win_rate_delta_vs_baseline * 100).toFixed(1)} puan
                    </td>
                    <td className="py-2 pr-4 text-ink-soft">{p.sample_size}</td>
                    <td className="py-2 pr-4">
                      {p.max_shared_trade_overlap_pct > 0 ? (
                        <span
                          className={p.max_shared_trade_overlap_pct >= 0.8 ? "text-fall" : "text-ink-soft"}
                          title={p.max_shared_trade_overlap_with ? `Şununla: ${p.max_shared_trade_overlap_with.join(" + ")}` : undefined}
                        >
                          %{(p.max_shared_trade_overlap_pct * 100).toFixed(0)}
                        </span>
                      ) : (
                        <span className="text-ink-faint">—</span>
                      )}
                    </td>
                    <td className="py-2 pr-4">
                      {p.distinct_days != null ? (
                        <span className={p.distinct_days < 5 ? "text-fall" : "text-ink-soft"}>{p.distinct_days}</span>
                      ) : (
                        <span className="text-ink-faint">—</span>
                      )}
                    </td>
                    <td className="py-2 pr-4">
                      {p.fdr_significant ? <Badge tone="rise">geçti ✓</Badge> : <Badge tone="neutral">elendi</Badge>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card>
        <h3 className="text-sm font-semibold text-ink mb-1">Haftalık rapor geçmişi</h3>
        <p className="text-xs text-ink-soft mb-3">
          services/tasks.py::refresh_agent_combination_reliability_report_task her hafta bir anlık görüntü
          kaydediyor — "hangi ajan grubunun güvenilirliği zaman içinde nasıl değişti" sorusunu cevaplamak için.
        </p>
        {reports.length === 0 ? (
          <EmptyState label="Henüz hiçbir haftalık rapor oluşmadı — ilk rapor bir sonraki periyodik çalışmada kaydedilecek." />
        ) : (
          <div className="flex flex-col gap-2">
            {reports.map((r) => (
              <div key={r.id} className="text-xs text-ink-soft flex items-center justify-between border-b border-line-soft/50 pb-2">
                <span>{new Date(r.created_at).toLocaleString()}</span>
                <span>
                  {r.result.pairs?.length ?? 0} grup · {r.result.n_trades ?? 0} işlem incelendi
                </span>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
