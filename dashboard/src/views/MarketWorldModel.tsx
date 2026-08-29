import { useEffect, useState } from "react";
import { authHeaders } from "../api/auth";
import { Badge, Card, PageHeader, EmptyState, ErrorNote, Spinner } from "../components/ui";

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
  p1_cumulative_return: number;
  p5_cumulative_return: number;
  p95_cumulative_return: number;
  worst_cumulative_return: number;
  cvar_5_cumulative_return: number;
  mean_max_drawdown: number;
  worst_max_drawdown: number;
  mean_loss_streak: number;
  worst_loss_streak: number;
};

// Faz 369-devam — GPT dış rapor önerisi: "En kritik eksik drawdown + loss
// streak + CVaR ve block-size sensitivity testi." block=5/10/20/30 taraması
// AYNI gerçek getiri dizisini SADECE block_size'ı değiştirerek tekrar
// çalıştırır — p5 sonuçları stabil kalıyorsa güven artar, patlıyorsa risk
// ölçümünün kendisi block_size seçimine duyarlı demektir.
type BlockSizeSensitivity = {
  by_block_size: Record<string, Paths>;
  is_stable: boolean | null;
  p5_sensitivity_ratio: number | null;
};

type Result = {
  block_size: number; path_length: number; n_returns: number; paths: Paths | null;
  block_size_sensitivity: BlockSizeSensitivity | null;
};
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
          işlem getirisi üzerinden 1000 yeniden-örneklenmiş yol. Her işlemin GERÇEK (kaldıraçlı) dolar PnL'i, sabit bir taban
          sermayeye (starting_capital) göre ölçülüyor — ham fiyat hareketi değil; ama "bileşik faiz" gibi her işlemde TÜM
          bakiyenin yeniden yatırıldığı da varsayılmıyor (gerçek sabit-oranlı pozisyon boyutlandırmasıyla tutarlı).
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

            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-6 pt-4 border-t border-line-soft">
              <div>
                <p className="text-xs text-ink-faint">p1 (uç kötümser)</p>
                <p className="text-sm font-mono text-fall">{(live.paths.p1_cumulative_return * 100).toFixed(2)}%</p>
              </div>
              <div>
                <p className="text-xs text-ink-faint">CVaR %5 (kuyruk ortalaması)</p>
                <p className="text-sm font-mono text-fall">{(live.paths.cvar_5_cumulative_return * 100).toFixed(2)}%</p>
              </div>
              <div>
                <p className="text-xs text-ink-faint">En kötü max drawdown</p>
                <p className="text-sm font-mono text-fall">{(live.paths.worst_max_drawdown * 100).toFixed(2)}%</p>
              </div>
              <div>
                <p className="text-xs text-ink-faint">En uzun kayıp serisi</p>
                <p className="text-sm font-mono text-ink-soft">{live.paths.worst_loss_streak} işlem</p>
              </div>
            </div>
            <p className="text-xs text-ink-faint mt-2 italic">
              CVaR (Expected Shortfall), p5 sınırının ALTINDA kalan tüm yolların ortalamasıdır — "en kötü %5
              gerçekleşirse ortalama kayıp ne kadar" sorusuna cevap verir, tek bir uç nokta değil. Max drawdown
              ve kayıp serisi, aynı p5'e sahip iki senaryonun operasyonel olarak farklı risk taşıyabileceğini
              (dağınık küçük kayıplar vs. uzun kesintisiz bir seri) gösterir.
            </p>
          </>
        )}
      </Card>

      <Card className="mb-6">
        <h3 className="text-sm font-semibold text-ink mb-1">Block-size duyarlılık testi</h3>
        <p className="text-xs text-ink-soft mb-3">
          AYNI gerçek getiri dizisi, SADECE block uzunluğu (5/10/20/30) değiştirilerek tekrar simüle ediliyor.
          p5 sonuçları stabil kalıyorsa risk ölçümüne güven artar; büyük ölçüde değişiyorsa (oran &gt;2×), risk
          ölçümünün kendisi block-size seçimine duyarlı demektir — tek bir block=10 sayısına körü körüne
          güvenilmemeli.
        </p>
        {loading ? (
          <Spinner />
        ) : !live?.block_size_sensitivity || Object.keys(live.block_size_sensitivity.by_block_size).length === 0 ? (
          <EmptyState label="Duyarlılık taraması için yeterli veri yok." />
        ) : (
          <>
            <div className="mb-3">
              {live.block_size_sensitivity.is_stable === null ? (
                <Badge tone="neutral">Değerlendirilemedi — yetersiz block_size çeşitliliği</Badge>
              ) : live.block_size_sensitivity.is_stable ? (
                <Badge tone="rise">Stabil (oran {live.block_size_sensitivity.p5_sensitivity_ratio}×)</Badge>
              ) : (
                <Badge tone="fall">Duyarlı — dikkat (oran {live.block_size_sensitivity.p5_sensitivity_ratio}×)</Badge>
              )}
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-ink-faint text-left border-b border-line-soft">
                    <th className="py-2 pr-4">Block size</th>
                    <th className="py-2 pr-4">p5</th>
                    <th className="py-2 pr-4">En kötü</th>
                    <th className="py-2 pr-4">Max drawdown (en kötü)</th>
                    <th className="py-2 pr-4">En uzun kayıp serisi</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(live.block_size_sensitivity.by_block_size)
                    .sort((a, b) => Number(a[0]) - Number(b[0]))
                    .map(([bs, p]) => (
                      <tr key={bs} className="border-b border-line-soft/50">
                        <td className="py-2 pr-4 font-mono text-ink">{bs}</td>
                        <td className="py-2 pr-4 font-mono text-fall">{(p.p5_cumulative_return * 100).toFixed(2)}%</td>
                        <td className="py-2 pr-4 font-mono text-fall">{(p.worst_cumulative_return * 100).toFixed(2)}%</td>
                        <td className="py-2 pr-4 font-mono text-fall">{(p.worst_max_drawdown * 100).toFixed(2)}%</td>
                        <td className="py-2 pr-4 font-mono text-ink-soft">{p.worst_loss_streak} işlem</td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
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
