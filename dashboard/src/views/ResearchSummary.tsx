import { useState } from "react";
import { authHeaders } from "../api/auth";
import { Button, Card, EmptyState, ErrorNote, PageHeader, Spinner } from "../components/ui";

// Faz 326 — kullanıcı isteği: "hepsini parça parça görüntülemek yerine
// tek bir pencereden erişebilsem... tek seferde bir düğmeye bastığımda
// hepsiyle ilgili genel bir rapor alsam." 10 Grup B (ölçüm-only)
// araştırma modülünün hepsini GERÇEK ZAMANLI (kullanıcı kararı: canlı
// hesapla, eski bir anlık görüntü değil) tek istekte topluyor — detaylar
// yine kendi sayfalarında, "Detaya git" ile oraya atlanabiliyor.
type ModuleEntry = {
  key: string;
  label: string;
  view: string;
  result: unknown;
  error: string | null;
};

export default function ResearchSummary({ onNavigate }: { onNavigate: (view: string) => void }) {
  const [modules, setModules] = useState<ModuleEntry[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [elapsedSec, setElapsedSec] = useState<number | null>(null);

  const generate = () => {
    setLoading(true);
    setError(null);
    const startedAt = Date.now();
    fetch("/api/v1/research-summary/", { headers: authHeaders() })
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((data) => {
        setModules(data.modules || []);
        setElapsedSec(Math.round((Date.now() - startedAt) / 1000));
      })
      .catch((e) => setError(String(e.message || e)))
      .finally(() => setLoading(false));
  };

  return (
    <div>
      <PageHeader
        title="Genel Özet"
        description="10 Grup B (ölçüm-only) araştırma modülünün hepsini tek seferde, GERÇEK ZAMANLI çalıştırıp TAM VERİYİ (özetlenmeden) gösterir — bazı modüller tüm watchlist'i taradığı için tam rapor 1-2 dakika sürebilir. Kendi sayfalarına da 'Detaya git' ile atlanabilir."
        action={
          <Button onClick={generate} disabled={loading}>
            {loading ? "Rapor oluşturuluyor…" : "Rapor Oluştur"}
          </Button>
        }
      />

      {error && <ErrorNote>{error}</ErrorNote>}

      {loading && (
        <div className="flex flex-col items-center gap-3 py-16">
          <Spinner />
          <p className="text-xs text-ink-faint">10 modül paralel hesaplanıyor, bazıları (ör. TP/SL Confluence, Causal Inference) tüm watchlist'i tarıyor — birkaç dakika sürebilir.</p>
        </div>
      )}

      {!loading && !modules && !error && (
        <EmptyState label="Henüz oluşturulmadı — yukarıdaki düğmeye basarak 10 araştırma modülünün canlı özetini alın." />
      )}

      {!loading && modules && (
        <>
          {elapsedSec !== null && (
            <p className="text-xs text-ink-faint mb-4">{elapsedSec} saniyede oluşturuldu — {new Date().toLocaleTimeString()}</p>
          )}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {modules.map((m) => (
              <Card key={m.key}>
                <div className="flex items-start justify-between gap-2 mb-2">
                  <h3 className="text-sm font-semibold text-ink">{m.label}</h3>
                  <button
                    onClick={() => onNavigate(m.view)}
                    className="text-xs text-accent-ink hover:underline shrink-0"
                  >
                    Detaya git →
                  </button>
                </div>
                {m.error ? (
                  <p className="text-xs text-fall">Geçici olarak alınamadı: {m.error}</p>
                ) : (
                  // Kullanıcı isteği (2026-08-28): "gelen raporlar bütün
                  // detaylarıyla gelsin, özet olarak gelmesin — bütün veriyi
                  // tek seferde toplu çekip görebileyim." Önceki summarizeResult()
                  // (hâlâ aşağıda, artık kullanılmıyor) her modülü 5 satıra/birkaç
                  // alt-öğeye kırpıyordu — ham veri (m.result, kendi sayfasıyla
                  // BİREBİR aynı) zaten backend'den tam geliyordu, sadece burada
                  // budanıyordu. Artık tam JSON, kaydırılabilir bir blokta.
                  <div className="max-h-96 overflow-auto rounded-lg bg-canvas-soft border border-line-soft">
                    <pre className="text-[11px] text-ink-soft font-mono p-3 whitespace-pre-wrap break-words">
                      {JSON.stringify(m.result, null, 2)}
                    </pre>
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
