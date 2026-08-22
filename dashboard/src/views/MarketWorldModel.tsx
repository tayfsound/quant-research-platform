import { useEffect, useState } from "react";
import { authHeaders } from "../api/auth";
import { Card, PageHeader, EmptyState, ErrorNote, Spinner } from "../components/ui";

// Cognitive Core 5.0-6.0 (Faz 901-940) — kullanıcı onayıyla (2026-08-19)
// 4 Grup B modülü birlikte canlıya alındı. risk/predictive/monte_carlo.py
// GERÇEK geçmiş getirilerden bootstrap örnekleme yapıyor ama TEKİL (iid)
// noktaları yeniden örnekliyor — getiriler arasındaki ardışık bağımlılığı
// (volatilite kümelenmesi) yok ediyor. Bu sayfa, Moving Block Bootstrap
// (Künsch, 1989) ile ARDIŞIK BLOKLAR yeniden örnekleyip gerçek zaman-serisi
// yapısını koruyan bir kümülatif getiri dağılımı gösterir. Sadece
// simülasyon/rapor, hiçbir pozisyon/risk kararı otomatik değişmiyor.
//
// Faz 350 — kozmetik yeniden çerçeveleme (harici bir mimari incelemenin
// bulgusu, kullanıcıyla doğrulandı): hesaplama (analytics/market_world_
// model.py) DEĞİŞMEDİ, hâlâ aynı geçerli Moving Block Bootstrap. Ama
// "Ortalama kümülatif getiri" gibi bir sayı (path_length=50 ardışık
// İŞLEMİN ham fiyat-hareketi bileşimi, pozisyon boyutu/kaldıraç dahil
// DEĞİL) kolayca "%1563 getiri tahmini" gibi okunup yanlış anlaşılabilir
// — oysa bu bir GETİRİ TAHMİNİ değil, aynı istatistiksel süreçten art
// arda işlem gelirse sonuçların ne kadar GENİŞ bir dağılıma yayılabileceğini
// gösteren bir RİSK simülatörü. Sayfa artık kötü-senaryo (p5/en kötü)
// metriklerini öne çıkarıyor, "ortalama"yı ikincil gösteriyor ve bunu
// açıkça belirten bir not içeriyor.
type Paths = {
  mean_cumulative_return: number;
  p5_cumulative_return: number;
  p95_cumulative_return: number;
  worst_cumulative_return: number;
};

type Result = { block_size: number; path_length: number; n_returns: number; paths: Paths | null };
type Report = { id: string; created_at: string; result: Result };

export default function MarketWorldModel() {
  const [live, setLive] = useState<Result | null>(null);
  const [reports, setReports] = useState<Report[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    setError(null);
    Promise.all([
      fetch("/api/v1/market-world-model/", { headers: authHeaders() }).then((r) => r.json()),
      fetch("/api/v1/market-world-model/reports?limit=20", { headers: authHeaders() }).then((r) => r.json()),
    ])
      .then(([liveData, history]) => {
        setLive(liveData.result || null);
        setReports(history.reports || []);
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  return (
    <div>
      <PageHeader
        title="Risk Simülatörü"
        description="Moving Block Bootstrap (Künsch, 1989) — gerçek kapanmış işlemlerin ardışık bağımlılığını koruyan bir kötü-senaryo simülasyonu. Bir getiri TAHMİNİ değil: aynı istatistiksel süreçten art arda işlem gelirse sonuçlar ne kadar geniş bir aralığa yayılabilir sorusuna cevap. Sadece rapor, hiçbir pozisyon/risk kararı otomatik değişmiyor."
      />

      {error && <ErrorNote>{error}</ErrorNote>}

      <Card className="mb-6">
        <h3 className="text-sm font-semibold text-ink mb-1">Canlı ölçüm</h3>
        <p className="text-xs text-ink-soft mb-3">
          Blok uzunluğu {live?.block_size ?? "—"}, yol uzunluğu {live?.path_length ?? "—"} ardışık işlem — {live?.n_returns ?? 0} gerçek
          işlem getirisi üzerinden 1000 yeniden-örneklenmiş yol. Pozisyon boyutu/kaldıraç dahil değil — ham fiyat hareketlerinin
          bileşimi, gerçek kasa büyüklüğü DEĞİL.
        </p>

        {loading ? (
          <Spinner />
        ) : !live || !live.paths ? (
          <EmptyState label="Henüz yeterli getiri verisi yok (block_size*2'nin altında)." />
        ) : (
          <>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div>
                <p className="text-xs text-ink-faint">En kötü yol</p>
                <p className="text-lg font-mono text-fall">{(live.paths.worst_cumulative_return * 100).toFixed(2)}%</p>
              </div>
              <div>
                <p className="text-xs text-ink-faint">p5 (kötümser senaryo)</p>
                <p className="text-lg font-mono text-fall">{(live.paths.p5_cumulative_return * 100).toFixed(2)}%</p>
              </div>
              <div>
                <p className="text-xs text-ink-faint">p95 (iyimser senaryo)</p>
                <p className="text-lg font-mono text-rise">{(live.paths.p95_cumulative_return * 100).toFixed(2)}%</p>
              </div>
              <div>
                <p className="text-xs text-ink-faint">Ortalama senaryo</p>
                <p className="text-lg font-mono text-ink-soft">{(live.paths.mean_cumulative_return * 100).toFixed(2)}%</p>
              </div>
            </div>
            <p className="text-xs text-ink-faint mt-3 italic">
              Bu bir portföy getirisi tahmini değildir — asıl bakılması gereken p5/en kötü yoldur (kuyruk riski).
              "Ortalama" burada bileşik (compounding) etkisiyle abartılı görünebilir, kasa yönetimi kararına
              girdi olarak KULLANILMAMALIDIR.
            </p>
          </>
        )}
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
                <span className="font-mono">
                  {r.result.n_returns} getiri
                  {r.result.paths ? ` · ort. ${(r.result.paths.mean_cumulative_return * 100).toFixed(2)}%` : ""}
                </span>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
