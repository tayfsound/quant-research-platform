import { useEffect, useState } from "react";
import { authHeaders } from "../api/auth";
import { Card, PageHeader, Badge, EmptyState, ErrorNote, Spinner } from "../components/ui";

// Faz 346 — Autonomous Strategy Synthesizer v1 "Regime Gate Discovery".
// Kullanıcı vizyonu ("belirli koşullar birlikteyken hafızaya bakıp
// tanısın") + kullanıcı onayı (netleştirme sorusu): v1 kapsamı bugün
// elle yapılan sürecin (SHORT/bearish_low bulgusu, Faz 342) otomasyonu.
// KASITLI OLARAK SADECE ölçüm/aday üretimi — hiçbir aday burada
// otomatik bir gate'e bağlanmıyor, tek çıktı bu rapor. Bir adayı
// gerçek bir kod değişikliğine dönüştürmek HER ZAMAN ayrı, açık bir
// insan kararı gerektirir.
type OutOfSample = {
  train_win_rate: number | null;
  train_sample_size: number | null;
  test_win_rate: number | null;
  test_sample_size: number | null;
  test_delta_vs_rest: number | null;
  replicated_out_of_sample: boolean;
};

type Candidate = {
  strategy: string;
  market_regime: string;
  sample_size: number;
  win_rate: number;
  rest_win_rate: number;
  delta_vs_rest: number;
  p_value: number;
  out_of_sample: OutOfSample;
};

type Result = {
  candidates: Candidate[];
  n_decisions_analyzed: number;
};

function pct(v: number | null): string {
  return v === null ? "—" : `${(v * 100).toFixed(1)}%`;
}

export default function StrategyHypothesisScanner() {
  const [result, setResult] = useState<Result | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    fetch("/api/v1/strategy-hypothesis-scanner/", { headers: authHeaders() })
      .then((r) => r.json())
      .then((data) => setResult(data.result || null))
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div>
      <PageHeader
        title="Strateji Hipotez Tarayıcı"
        description="Autonomous Strategy Synthesizer v1 — strategy × rejim uzayını otomatik tarayıp istatistiksel olarak sağlam (FDR-düzeltmeli), ekonomik olarak anlamlı, zaman-bölünmüş OOS testinden geçmiş kötü kombinasyonları bulur. SADECE araştırma çıktısı — hiçbir aday otomatik olarak canlı bir karara bağlanmıyor, gerçek bir düzeltme her zaman ayrı bir insan kararı gerektirir."
      />

      {error && <ErrorNote>{error}</ErrorNote>}

      {loading ? (
        <Spinner />
      ) : !result || result.candidates.length === 0 ? (
        <EmptyState label="Şu an istatistiksel olarak sağlam bir aday yok — bu iyi bir haber, mevcut sistemde tespit edilmemiş büyük bir regime-gate boşluğu bulunamadı." />
      ) : (
        <>
          <p className="text-xs text-ink-faint mb-4">
            {result.n_decisions_analyzed} kapanmış karar tarandı (zaman sırasına göre).
          </p>
          {result.candidates.map((c, i) => (
            <Card key={i} className="mb-4">
              <div className="flex items-center gap-2 mb-2">
                <h3 className="text-sm font-semibold text-ink">
                  {c.strategy} × {c.market_regime}
                </h3>
                <Badge tone="fall">aday: performans düşürücü gate</Badge>
                {c.out_of_sample.replicated_out_of_sample ? (
                  <Badge tone="rise">OOS'ta tekrarlandı</Badge>
                ) : (
                  <Badge tone="warn">OOS'ta henüz tekrarlanmadı</Badge>
                )}
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <tbody>
                    <tr className="border-b border-line-soft/50">
                      <td className="py-1.5 pr-4 text-ink-faint">Hücre isabeti (n={c.sample_size})</td>
                      <td className="py-1.5 pr-4 font-mono text-fall">{pct(c.win_rate)}</td>
                    </tr>
                    <tr className="border-b border-line-soft/50">
                      <td className="py-1.5 pr-4 text-ink-faint">Geri kalan isabeti (kontaminasyonsuz)</td>
                      <td className="py-1.5 pr-4 font-mono text-ink">{pct(c.rest_win_rate)}</td>
                    </tr>
                    <tr className="border-b border-line-soft/50">
                      <td className="py-1.5 pr-4 text-ink-faint">Fark</td>
                      <td className="py-1.5 pr-4 font-mono text-fall">{pct(c.delta_vs_rest)}</td>
                    </tr>
                    <tr className="border-b border-line-soft/50">
                      <td className="py-1.5 pr-4 text-ink-faint">p-değeri (FDR-düzeltmeli anlamlı)</td>
                      <td className="py-1.5 pr-4 font-mono text-ink">{c.p_value.toFixed(6)}</td>
                    </tr>
                    <tr className="border-b border-line-soft/50">
                      <td className="py-1.5 pr-4 text-ink-faint">OOS train / test isabeti</td>
                      <td className="py-1.5 pr-4 font-mono text-ink">
                        {pct(c.out_of_sample.train_win_rate)} (n={c.out_of_sample.train_sample_size ?? "—"}) →{" "}
                        {pct(c.out_of_sample.test_win_rate)} (n={c.out_of_sample.test_sample_size ?? "—"})
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </Card>
          ))}
        </>
      )}
    </div>
  );
}
