import { useState } from "react";
import { authHeaders } from "../api/auth";
import { Badge, Button, Card, EmptyState, ErrorNote, PageHeader, Spinner } from "../components/ui";

// Faz 415 (2026-09-06) — kullanıcı isteği: "son eklediğimiz modüllerden
// aldığımız verilerin zaman içindeki tutarlılığını gösteren verileri
// dashboard'da göremiyorum." Faz 407 (compute_stability) kasıtlı olarak
// backend-only kalmıştı, hiçbir görünüm kapsamda değildi — TP/SL
// Confluence'ın (Faz 409) aynı "ölçülüyor ama görünmez" boşluğu. Bu
// sayfa YENİ bir hesaplama yapmıyor, ResearchSummary ile AYNI canlı/
// buton-tetiklemeli desende zaten var olan *_stability alanlarını
// düz bir listede gösteriyor.
type StabilityField = {
  path: string;
  n: number;
  mean: number;
  std: number;
  min: number;
  max: number;
  coefficient_of_variation: number | null;
};

type ModuleEntry = {
  key: string;
  label: string;
  fields: StabilityField[];
  n_fields: number;
  last_computed_at: string | null;
  error: string | null;
};

type VolatileField = StabilityField & { module_key: string; module_label: string };

// Faz 435 (2026-09-07) — kullanıcı isteği: dashboard'da N ile CV her
// zaman birlikte gösterilsin, düşük N + iyi-görünen CV durumu görsel
// olarak uyarsın. Bugünkü GERÇEK örnek tam bu: correlation_stability
// n=2 (Faz 432'den önce, ham/örtüşen snapshot'larla n=12) CV=0,00098
// gösteriyordu — "çok istikrarlı" görünüp aslında sadece 2 (ya da daha
// az) gerçekten bağımsız gözleme dayanıyordu. Eşik (5), oturum boyunca
// tekrarlanan min_distinct_days=5 ile AYNI — "en az 5 bağımsız gözlem"
// bu kod tabanında zaten kanıtlanmış bir taban.
const LOW_N_THRESHOLD = 5;

function cvTone(cv: number | null, n: number): "rise" | "warn" | "fall" | "neutral" {
  if (n < LOW_N_THRESHOLD) return "warn";
  if (cv === null) return "neutral";
  if (cv < 0.15) return "rise";
  if (cv < 0.5) return "warn";
  return "fall";
}

function cvLabel(cv: number | null, n: number): string {
  if (n < LOW_N_THRESHOLD) return cv === null ? `n=${n} — az veri` : `CV ${cv.toFixed(3)} (n=${n}, az veri)`;
  if (cv === null) return "—";
  return `CV ${cv.toFixed(3)}`;
}

function NCell({ n }: { n: number }) {
  return (
    <td
      className={`py-1.5 pr-3 tabular-nums ${n < LOW_N_THRESHOLD ? "text-warn font-semibold" : "text-ink-faint"}`}
      title={n < LOW_N_THRESHOLD ? `Sadece ${n} gözlem — güvenilir bir istikrar sonucu için yetersiz (taban: ${LOW_N_THRESHOLD})` : undefined}
    >
      {n}
    </td>
  );
}

function FieldRow({ f }: { f: StabilityField }) {
  return (
    <tr className="border-t border-line-soft">
      <td className="py-1.5 pr-3 text-ink-soft font-mono text-[11px] break-all">{f.path}</td>
      <NCell n={f.n} />
      <td className="py-1.5 pr-3 text-ink-soft tabular-nums">{f.mean.toFixed(4)}</td>
      <td className="py-1.5">
        <Badge tone={cvTone(f.coefficient_of_variation, f.n)}>{cvLabel(f.coefficient_of_variation, f.n)}</Badge>
      </td>
    </tr>
  );
}

export default function MeasurementStability() {
  const [modules, setModules] = useState<ModuleEntry[] | null>(null);
  const [mostVolatile, setMostVolatile] = useState<VolatileField[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [elapsedSec, setElapsedSec] = useState<number | null>(null);

  const generate = () => {
    setLoading(true);
    setError(null);
    const startedAt = Date.now();
    fetch("/api/v1/measurement-stability/", { headers: authHeaders() })
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((data) => {
        setModules(data.modules || []);
        setMostVolatile(data.most_volatile || []);
        setElapsedSec(Math.round((Date.now() - startedAt) / 1000));
      })
      .catch((e) => setError(String(e.message || e)))
      .finally(() => setLoading(false));
  };

  const modulesWithData = (modules || []).filter((m) => m.n_fields > 0);
  const modulesWithoutData = (modules || []).filter((m) => m.n_fields === 0 && !m.error);

  return (
    <div>
      <PageHeader
        title="Ölçüm Stabilitesi"
        description="Sistemin ölçtüğü her nokta-tahminin (korelasyon, isabet oranı, Brier skoru, IC…) zaman içinde ne kadar istikrarlı (aynı okumaya yakın kalıyor) olduğunu gösterir. Faz 407: gözlem-only, hiçbir canlı kararı değiştirmiyor."
        action={
          <Button onClick={generate} disabled={loading}>
            {loading ? "Taranıyor…" : "Taze Tara"}
          </Button>
        }
      />
      {/* Faz 435 (2026-09-07) — kullanıcı isteği: "Modül tanımını
          netleştir: Stability ≠ Reliability, ayrı bir iddia." Bu sayfa
          bir ölçümün DOĞRU olduğunu değil, zaman içinde TUTARLI
          kaldığını gösteriyor — sistematik olarak yanlış ama istikrarlı
          bir ölçüm mükemmel bir CV alabilir (bkz. n<{LOW_N_THRESHOLD}
          uyarısı: az veriyle "istikrarlı" görünen bir ölçüm hem yanlış
          hem yanıltıcı derecede güvenli görünebilir). */}
      <p className="text-xs text-ink-faint mb-4 max-w-3xl">
        İstikrar (stability) doğruluk (reliability) DEĞİLDİR — burada düşük CV, ölçümün zaman içinde tutarlı
        kaldığını gösterir, ölçümün doğru/isabetli olduğunu değil. Ayrıca n&lt;{LOW_N_THRESHOLD} olan satırlar
        turuncu uyarılıdır — çok az gözleme dayanan bir CV yanıltıcı derecede istikrarlı görünebilir.
      </p>

      {error && <ErrorNote>{error}</ErrorNote>}

      {loading && (
        <div className="flex flex-col items-center gap-3 py-16">
          <Spinner />
          <p className="text-xs text-ink-faint">~20 modül paralel taranıyor, birkaç dakika sürebilir.</p>
        </div>
      )}

      {!loading && !modules && !error && (
        <EmptyState label="Henüz taranmadı — yukarıdaki düğmeye basarak tüm modüllerin stabilite durumunu görün." />
      )}

      {!loading && modules && (
        <>
          {elapsedSec !== null && (
            <p className="text-xs text-ink-faint mb-4">{elapsedSec} saniyede tarandı — {new Date().toLocaleTimeString()}</p>
          )}

          {mostVolatile && mostVolatile.length > 0 && (
            <Card className="mb-4">
              <h3 className="text-sm font-semibold text-ink mb-3">En Oynak 15 Ölçüm (dikkatli okunmalı)</h3>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-left text-ink-faint">
                      <th className="py-1.5 pr-3 font-medium">Modül</th>
                      <th className="py-1.5 pr-3 font-medium">Alan</th>
                      <th className="py-1.5 pr-3 font-medium">n</th>
                      <th className="py-1.5 font-medium">İstikrar</th>
                    </tr>
                  </thead>
                  <tbody>
                    {mostVolatile.map((f, i) => (
                      <tr key={i} className="border-t border-line-soft">
                        <td className="py-1.5 pr-3 text-ink-soft">{f.module_label}</td>
                        <td className="py-1.5 pr-3 text-ink-soft font-mono text-[11px] break-all">{f.path}</td>
                        <NCell n={f.n} />
                        <td className="py-1.5">
                          <Badge tone={cvTone(f.coefficient_of_variation, f.n)}>{cvLabel(f.coefficient_of_variation, f.n)}</Badge>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}

          {modulesWithoutData.length > 0 && (
            <Card className="mb-4">
              <h3 className="text-sm font-semibold text-ink mb-2">Henüz stabilite verisi yok</h3>
              <p className="text-xs text-ink-faint mb-2">
                Bu modüller çalışıyor ama yeterli geçmiş anlık görüntü birikmedi (bazıları haftalık kadansta — ör.
                Feature IC, Korelasyon) — "her şey yolunda" değil, sadece henüz ölçülemiyor.
              </p>
              <div className="flex flex-wrap gap-2">
                {modulesWithoutData.map((m) => (
                  <Badge key={m.key} tone="neutral">
                    {m.label}
                    {m.last_computed_at && ` — son: ${new Date(m.last_computed_at).toLocaleDateString()}`}
                  </Badge>
                ))}
              </div>
            </Card>
          )}

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {modulesWithData.map((m) => (
              <Card key={m.key}>
                <div className="flex items-start justify-between gap-2 mb-2">
                  <h3 className="text-sm font-semibold text-ink">{m.label}</h3>
                  <span className="text-xs text-ink-faint shrink-0">{m.n_fields} alan</span>
                </div>
                {m.error ? (
                  <p className="text-xs text-fall">Geçici olarak alınamadı: {m.error}</p>
                ) : (
                  <div className="max-h-80 overflow-auto">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="text-left text-ink-faint sticky top-0 bg-canvas">
                          <th className="py-1.5 pr-3 font-medium">Alan</th>
                          <th className="py-1.5 pr-3 font-medium">n</th>
                          <th className="py-1.5 pr-3 font-medium">Ortalama</th>
                          <th className="py-1.5 font-medium">İstikrar</th>
                        </tr>
                      </thead>
                      <tbody>
                        {m.fields.map((f, i) => (
                          <FieldRow key={i} f={f} />
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </Card>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
