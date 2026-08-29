import { useEffect, useState } from "react";
import { authHeaders } from "../api/auth";
import { Card, PageHeader, Badge, EmptyState, ErrorNote, Spinner } from "../components/ui";

// Cognitive Core 2.0 / M4 (Faz 519-543) — kullanıcı onayıyla (2026-08-19)
// 4 Grup B modülü birlikte canlıya alındı. services/confidence_calibration.py
// GERÇEK ama sadece "kovaya göre gerçek doğruluk oranı"nı ölçüyor — bu
// sayfa Brier Score (Brier, 1950) ile hem kalibrasyonu hem çözünürlüğü
// TEK bir sayıda birleştiriyor. Sadece ölçüm/rapor.
type DomainScore = {
  brier_score: number; sample_size: number; better_than_random: boolean;
  // Faz 369-devam — GPT dış rapor bulgusu: mevcut brier_score HER ZAMAN
  // KALİBRE EDİLMİŞ confidence'tan hesaplanıyordu — ham sinyal hiç ayrı
  // ölçülemiyordu (kalibrasyon eğrisi de AYNI kalibre değerden bucket'lanıp
  // döngüsel çalışıyordu). raw_brier_score, calibrate_domain_confidence
  // ÖNCESİ ham değerden — SADECE bu değişiklikten SONRAKİ yeni kararlarda
  // birikir, yeterli örneklem toplanana kadar null.
  raw_brier_score: { brier_score: number; sample_size: number; better_than_random: boolean } | null;
};
type Result = { by_domain: Record<string, DomainScore> };
type Report = { id: string; created_at: string; result: Result };

export default function DirectionPredictionV2() {
  const [live, setLive] = useState<Result | null>(null);
  const [reports, setReports] = useState<Report[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    setError(null);
    Promise.all([
      fetch("/api/v1/direction-prediction-v2/", { headers: authHeaders() }).then((r) => r.json()),
      fetch("/api/v1/direction-prediction-v2/reports?limit=20", { headers: authHeaders() }).then((r) => r.json()),
    ])
      .then(([liveData, history]) => {
        setLive(liveData.result || null);
        setReports(history.reports || []);
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const domains = live ? Object.entries(live.by_domain).sort((a, b) => a[1].brier_score - b[1].brier_score) : [];

  return (
    <div>
      <PageHeader
        title="Direction Prediction v2"
        description="Brier Score (Brier, 1950) — her ajanın (confidence, gerçek sonuç) çiftlerinden hesaplanan olasılıksal tahmin kalitesi. 0 mükemmel, 0.25 rastgele (p=0.5 sabit tahmin), 1.0 en kötü. Sadece ölçüm/rapor."
      />

      {error && <ErrorNote>{error}</ErrorNote>}

      <Card className="mb-6">
        <h3 className="text-sm font-semibold text-ink mb-1">Canlı ölçüm — ajan başına</h3>
        <p className="text-xs text-ink-soft mb-3">En az 10 gerçek yönlü tahmin gerektirir, en iyiden (düşük skor) en kötüye sıralı.</p>

        {loading ? (
          <Spinner />
        ) : domains.length === 0 ? (
          <EmptyState label="Henüz yeterli örneklemli ajan yok." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-left text-ink-faint border-b border-line-soft">
                  <th className="py-2 pr-4">Ajan</th>
                  <th className="py-2 pr-4">Brier (kalibre edilmiş)</th>
                  <th className="py-2 pr-4">Brier (ham)</th>
                  <th className="py-2 pr-4">Örneklem</th>
                  <th className="py-2 pr-4">Rastgeleden iyi mi</th>
                </tr>
              </thead>
              <tbody>
                {domains.map(([domain, score]) => (
                  <tr key={domain} className="border-b border-line-soft/50">
                    <td className="py-2 pr-4 text-ink font-medium">{domain}</td>
                    <td className="py-2 pr-4 font-mono">{score.brier_score.toFixed(4)}</td>
                    <td className="py-2 pr-4 font-mono text-ink-soft">
                      {score.raw_brier_score ? (
                        score.raw_brier_score.brier_score.toFixed(4)
                      ) : (
                        <span className="text-ink-faint">henüz yeterli veri yok</span>
                      )}
                    </td>
                    <td className="py-2 pr-4">{score.sample_size}</td>
                    <td className="py-2 pr-4">
                      <Badge tone={score.better_than_random ? "rise" : "fall"}>
                        {score.better_than_random ? "Evet" : "Hayır"}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="text-xs text-ink-faint mt-3 italic">
          "Kalibre edilmiş" kolon, ajanın council'e girmeden hemen önce ampirik eğriden geçirilmiş
          confidence'ından hesaplanır — mevcut, uzun süredir izlenen metrik. "Ham" kolon, kalibrasyon ÖNCESİ
          orijinal beyandan hesaplanır (yeni eklendi — sadece bu değişiklikten sonraki kararlarda birikir).
          Ham skorun kalibre edilmişten belirgin şekilde KÖTÜ olması, kalibrasyonun gerçekten işe yaradığının
          kanıtıdır; ikisi neredeyse aynıysa, o ajan için kalibrasyon zaten az fark yaratıyor demektir.
        </p>
      </Card>

      <Card>
        <h3 className="text-sm font-semibold text-ink mb-1">Haftalık rapor geçmişi</h3>
        {reports.length === 0 ? (
          <EmptyState label="Henüz hiçbir haftalık rapor oluşmadı — ilk rapor bir sonraki periyodik çalışmada kaydedilecek." />
        ) : (
          <div className="flex flex-col gap-2">
            {reports.map((r) => (
              <div key={r.id} className="text-xs text-ink-soft flex items-center justify-between border-b border-line-soft/50 pb-2">
                <span>{new Date(r.created_at).toLocaleString()}</span>
                <span className="font-mono">{Object.keys(r.result.by_domain || {}).length} ajan</span>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
