import { useEffect, useState } from "react";
import { authHeaders } from "../api/auth";
import { Card, PageHeader, Badge, EmptyState, ErrorNote, Spinner } from "../components/ui";

// Faz 268-sonrası — kullanıcı isteği: "Feature IC'yi karar hattına
// bağlama." analytics/feature_ic.py::compute_feature_ic() her isimli
// sinyalin (ör. RSI, trend, liquidity_condition) GERÇEK kapanmış
// işlemlerdeki ileri getiriyle korelasyonunu (Information Coefficient)
// ölçüyor. Bu sayfa SADECE ölçüm/izleme — hiçbir feature'ı otomatik
// pasifleştirmiyor, hiçbir ajan skorlamasını değiştirmiyor. Yeterli
// gerçek veri birikip anlamlı (istatistiksel olarak anlamlı, p<0.05)
// bir bulgu çıktığında, bir insan bu sayıları görüp kasıtlı bir
// kalibrasyon kararı verebilir.
type FeatureICEntry = {
  ic: number;
  p_value: number;
  sample_size: number;
  agent_domain: string;
};

type FeatureICReport = {
  id: string;
  created_at: string;
  features: Record<string, FeatureICEntry>;
  total_closed_trades: number;
};

// Faz 368 — Feature Intelligence Layer Faz A. Gerçek veriyle doğrulandı:
// trend/ema_alignment/momentum/vwap_confirm/adx_strong_confirm birbirleriyle
// r=1.000 — yukarıdaki tablo bu 5 feature'ı 5 AYRI, bağımsız sinyal gibi
// gösteriyor ama aslında TEK bir ikili sinyalin 5 farklı ismi. Bu bölüm bu
// çakışmayı (redundancy matrisi) ve "b zaten biliniyorken a'nın kattığı EK
// bilgi" (koşullu IC) sorusunu görünür kılıyor.
type RedundancyEntry = { correlation: number; sample_size: number };
type ConditionalICEntry = { raw_ic: number; conditional_ic_given: Record<string, number | null> };

// Faz B (2026-08-29) — Koşullu IC'nin (SADECE ikili) ötesine geçen
// çoklu-değişkenli residualizasyon. compute_redundancy_clusters gerçek
// KLİKLERİ (hepsi birbiriyle mutually yüksek redundant — zincirleme
// DEĞİL) buluyor; bu feature'lar kümenin GERİ KALANINA göre birlikte
// residualize ediliyor. 3-4 üyeli, neredeyse birebir çakışan kümeler
// genelde rank-deficient çıkıp dürüstçe sonuç üretmiyor (tabloda hiç
// görünmez) — sadece sayısal olarak GERÇEKTEN ayrıştırılabilen çiftler/
// küçük kümeler görünür.
type ResidualizedICEntry = { cluster: string[]; residualized_ic: number; p_value: number; sample_size: number };

function residualizedIcTone(entry: ResidualizedICEntry): "rise" | "fall" | "neutral" {
  if (entry.p_value >= 0.05) return "neutral";
  return entry.residualized_ic >= 0 ? "rise" : "fall";
}

function redundancyTone(correlation: number): "fall" | "rise" | "neutral" {
  const abs = Math.abs(correlation);
  if (abs >= 0.9) return "fall"; // neredeyse birebir çakışma — kırmızı, dikkat
  if (abs >= 0.7) return "rise"; // eşik üstü, koşullu IC hesaplanıyor
  return "neutral";
}

function icTone(ic: number, pValue: number): "rise" | "fall" | "neutral" {
  if (pValue >= 0.05) return "neutral";
  return ic >= 0 ? "rise" : "fall";
}

// Koşullu IC için p-değeri hesaplanmıyor (Faz A kapalı-form kısmi
// korelasyon, anlamlılık testi Faz B'ye bırakıldı) — sadece işaret.
function partialIcTone(partial: number): "rise" | "fall" {
  return partial >= 0 ? "rise" : "fall";
}

export default function FeatureIC() {
  const [features, setFeatures] = useState<Record<string, FeatureICEntry>>({});
  const [reports, setReports] = useState<FeatureICReport[]>([]);
  const [redundancy, setRedundancy] = useState<Record<string, RedundancyEntry>>({});
  const [conditionalIC, setConditionalIC] = useState<Record<string, ConditionalICEntry>>({});
  const [residualizedIC, setResidualizedIC] = useState<Record<string, ResidualizedICEntry>>({});
  const [redundancyClusters, setRedundancyClusters] = useState<string[][]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    setError(null);
    Promise.all([
      fetch("/api/v1/feature-ic/", { headers: authHeaders() }).then((r) => r.json()),
      fetch("/api/v1/feature-ic/reports?limit=20", { headers: authHeaders() }).then((r) => r.json()),
      fetch("/api/v1/feature-relationship/", { headers: authHeaders() }).then((r) => r.json()),
    ])
      .then(([live, history, relationship]) => {
        setFeatures(live.features || {});
        setReports(history.reports || []);
        setRedundancy(relationship.redundancy || {});
        setConditionalIC(relationship.conditional_ic || {});
        setResidualizedIC(relationship.residualized_ic || {});
        setRedundancyClusters(relationship.redundancy_clusters || []);
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const sortedFeatures = Object.entries(features).sort((a, b) => a[1].ic - b[1].ic);
  const sortedRedundancy = Object.entries(redundancy).sort(
    (a, b) => Math.abs(b[1].correlation) - Math.abs(a[1].correlation)
  );

  return (
    <div>
      <PageHeader
        title="Feature IC"
        description="Her ajan sinyalinin GERÇEK kapanmış işlemlerdeki ileri getiriyle korelasyonu (Information Coefficient) + feature'ların birbirleriyle çakışması (redundancy) ve koşullu IC — sadece ölçüm/izleme, hiçbir feature otomatik pasifleştirilmiyor."
      />

      {error && <ErrorNote>{error}</ErrorNote>}

      <Card className="mb-6">
        <h3 className="text-sm font-semibold text-ink mb-1">Canlı ölçüm</h3>
        <p className="text-xs text-ink-soft mb-3">
          Her sorguda gerçek kapanmış işlem geçmişinden taze hesaplanır. Sadece yeterli örneklemi (≥20) olan
          feature'lar listelenir — istatistiksel olarak anlamsız bir sayı hiç gösterilmez.
        </p>

        {loading ? (
          <Spinner />
        ) : sortedFeatures.length === 0 ? (
          <EmptyState label="Henüz hiçbir feature için yeterli gerçek örneklem birikmedi." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-left text-ink-faint border-b border-line-soft">
                  <th className="py-2 pr-4">Feature</th>
                  <th className="py-2 pr-4">Ajan</th>
                  <th className="py-2 pr-4">IC</th>
                  <th className="py-2 pr-4">p-değeri</th>
                  <th className="py-2 pr-4">Örneklem</th>
                  <th className="py-2 pr-4">Anlamlılık</th>
                </tr>
              </thead>
              <tbody>
                {sortedFeatures.map(([name, entry]) => (
                  <tr key={name} className="border-b border-line-soft/50">
                    <td className="py-2 pr-4 font-mono text-ink">{name}</td>
                    <td className="py-2 pr-4 text-ink-soft">{entry.agent_domain}</td>
                    <td className="py-2 pr-4">
                      <Badge tone={icTone(entry.ic, entry.p_value)}>{entry.ic.toFixed(4)}</Badge>
                    </td>
                    <td className="py-2 pr-4 text-ink-soft">{entry.p_value.toFixed(4)}</td>
                    <td className="py-2 pr-4 text-ink-soft">{entry.sample_size}</td>
                    <td className="py-2 pr-4">
                      {entry.p_value < 0.05 ? (
                        <Badge tone="accent">anlamlı</Badge>
                      ) : (
                        <span className="text-ink-faint">yetersiz kanıt</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card className="mb-6">
        <h3 className="text-sm font-semibold text-ink mb-1">Redundancy matrisi</h3>
        <p className="text-xs text-ink-soft mb-3">
          Aynı işlemde BİRLİKTE ateşlenen feature çiftlerinin birbirleriyle (getiriyle değil) korelasyonu.
          |korelasyon| ≥ 0.9 neredeyse birebir çakışma demek — council'e ayrı ayrı oy gibi giriyorlar ama
          matematiksel olarak aynı sinyal.
        </p>
        {loading ? (
          <Spinner />
        ) : sortedRedundancy.length === 0 ? (
          <EmptyState label="Henüz hiçbir feature çifti için yeterli ortak örneklem birikmedi." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-left text-ink-faint border-b border-line-soft">
                  <th className="py-2 pr-4">Feature A</th>
                  <th className="py-2 pr-4">Feature B</th>
                  <th className="py-2 pr-4">Korelasyon</th>
                  <th className="py-2 pr-4">Örneklem</th>
                </tr>
              </thead>
              <tbody>
                {sortedRedundancy.map(([pairKey, entry]) => {
                  const [a, b] = pairKey.split("|");
                  return (
                    <tr key={pairKey} className="border-b border-line-soft/50">
                      <td className="py-2 pr-4 font-mono text-ink">{a}</td>
                      <td className="py-2 pr-4 font-mono text-ink">{b}</td>
                      <td className="py-2 pr-4">
                        <Badge tone={redundancyTone(entry.correlation)}>{entry.correlation.toFixed(4)}</Badge>
                      </td>
                      <td className="py-2 pr-4 text-ink-soft">{entry.sample_size}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card className="mb-6">
        <h3 className="text-sm font-semibold text-ink mb-1">Koşullu IC</h3>
        <p className="text-xs text-ink-soft mb-3">
          Yukarıdaki tabloda ≥0.7 redundant çıkan çiftler için: "diğer feature zaten biliniyorken bu
          feature'ın getiriye kattığı EK bilgi ne kadar" (kısmi korelasyon). Boş/"—" değer, çiftin neredeyse
          birebir aynı bilgiyi taşıdığı (payda sıfıra yaklaştığı) anlamına gelir.
        </p>
        {loading ? (
          <Spinner />
        ) : Object.keys(conditionalIC).length === 0 ? (
          <EmptyState label="≥0.7 redundant hiçbir çift yok — koşullu IC hesaplanacak bir şey bulunmadı." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-left text-ink-faint border-b border-line-soft">
                  <th className="py-2 pr-4">Feature</th>
                  <th className="py-2 pr-4">Ham IC</th>
                  <th className="py-2 pr-4">Koşullandırıldığı feature</th>
                  <th className="py-2 pr-4">Koşullu IC</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(conditionalIC).flatMap(([feature, entry]) =>
                  Object.entries(entry.conditional_ic_given).map(([other, partial]) => (
                    <tr key={`${feature}|${other}`} className="border-b border-line-soft/50">
                      <td className="py-2 pr-4 font-mono text-ink">{feature}</td>
                      <td className="py-2 pr-4 text-ink-soft">{entry.raw_ic.toFixed(4)}</td>
                      <td className="py-2 pr-4 font-mono text-ink-soft">{other}</td>
                      <td className="py-2 pr-4">
                        {partial === null ? (
                          <span className="text-ink-faint">—</span>
                        ) : (
                          <Badge tone={partialIcTone(partial)}>{partial.toFixed(4)}</Badge>
                        )}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card className="mb-6">
        <h3 className="text-sm font-semibold text-ink mb-1">Çoklu-değişkenli residualizasyon</h3>
        <p className="text-xs text-ink-soft mb-3">
          Koşullu IC (yukarıda) SADECE ikili — bir feature'ı TEK bir komşusuna göre koşullandırıyor. Burada
          gerçekten mutually-redundant (hepsi birbiriyle ≥0.7, zincirleme değil GERÇEK klik) küçük kümeler,
          KENDİ kümelerinin TAMAMINA göre birlikte residualize ediliyor — kalan (residual) getiriyle
          korelasyona giriyor. 3-4 üyeli, neredeyse birebir çakışan kümeler genelde sayısal olarak
          ayrıştırılamaz (rank-deficient) ve dürüstçe tabloda hiç görünmez — bu, veri eksikliği değil,
          feature'ların gerçekten ayırt edilemez olduğunun bir göstergesi.
        </p>
        {redundancyClusters.length > 0 && (
          <p className="text-xs text-ink-faint mb-3">
            Bulunan klikler:{" "}
            {redundancyClusters.map((c, i) => (
              <span key={i} className="font-mono">
                {c.join(" + ")}
                {i < redundancyClusters.length - 1 ? "; " : ""}
              </span>
            ))}
          </p>
        )}
        {loading ? (
          <Spinner />
        ) : Object.keys(residualizedIC).length === 0 ? (
          <EmptyState label="Sayısal olarak ayrıştırılabilen bir küme yok — kümeler ya çok küçük (henüz klik bulunamadı) ya da rank-deficient." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-left text-ink-faint border-b border-line-soft">
                  <th className="py-2 pr-4">Feature</th>
                  <th className="py-2 pr-4">Küme</th>
                  <th className="py-2 pr-4">Residualized IC</th>
                  <th className="py-2 pr-4">p-değeri</th>
                  <th className="py-2 pr-4">Örneklem</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(residualizedIC).map(([feature, entry]) => (
                  <tr key={feature} className="border-b border-line-soft/50">
                    <td className="py-2 pr-4 font-mono text-ink">{feature}</td>
                    <td className="py-2 pr-4 font-mono text-ink-soft">{entry.cluster.join(" + ")}</td>
                    <td className="py-2 pr-4">
                      <Badge tone={residualizedIcTone(entry)}>{entry.residualized_ic.toFixed(4)}</Badge>
                    </td>
                    <td className="py-2 pr-4 text-ink-soft">{entry.p_value.toFixed(4)}</td>
                    <td className="py-2 pr-4 text-ink-soft">{entry.sample_size}</td>
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
          services/tasks.py::refresh_feature_ic_report_task her hafta bir anlık görüntü kaydediyor — "IC
          zamanla nasıl değişti" sorusunu cevaplamak için.
        </p>
        {reports.length === 0 ? (
          <EmptyState label="Henüz hiçbir haftalık rapor oluşmadı — ilk rapor bir sonraki periyodik çalışmada kaydedilecek." />
        ) : (
          <div className="flex flex-col gap-2">
            {reports.map((r) => (
              <div key={r.id} className="text-xs text-ink-soft flex items-center justify-between border-b border-line-soft/50 pb-2">
                <span>{new Date(r.created_at).toLocaleString()}</span>
                <span>
                  {Object.keys(r.features).length} feature ölçüldü · {r.total_closed_trades} kapanmış işlem
                </span>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
