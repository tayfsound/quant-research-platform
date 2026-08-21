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

function isPlainObject(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

// Her modülün ham sonucundan (10 farklı şekil) kısa, okunabilir birkaç
// satırlık bir özet çıkarır — genel/şekil-agnostik bir sezgisel yöntem:
// sayı/metin/boolean alanları doğrudan, dict-of-dict alanlarında (ör.
// {bucket: {sample_size, win_rate}}) alt-kovaları "n=X, oran=%Y" olarak,
// liste alanlarında sadece eleman sayısını gösterir.
function summarizeResult(result: unknown): string[] {
  if (!isPlainObject(result)) return ["veri yok"];
  const lines: string[] = [];
  for (const [key, value] of Object.entries(result)) {
    if (lines.length >= 5) break;
    if (value === null || value === undefined) continue;
    if (typeof value === "number") {
      lines.push(`${key}: ${Number.isInteger(value) ? value : value.toFixed(4)}`);
    } else if (typeof value === "string" || typeof value === "boolean") {
      lines.push(`${key}: ${String(value)}`);
    } else if (Array.isArray(value)) {
      // Kullanıcı bulgusu (GPT raporu üzerinden): self_model'in
      // reliability_flags gibi PRİMİTİF (string/number) dizileri sadece
      // "1 öğe" olarak gösteriliyordu — "degraded" durumunun ASIL nedeni
      // (ör. "9_features_drifted") tamamen gizleniyordu. Primitif
      // dizilerde artık içerik gösteriliyor (uzunsa kırpılıyor), sadece
      // karmaşık/dict elemanlı dizilerde eski "N öğe" sayımına dönülüyor.
      const isPrimitiveArray = value.every((v) => typeof v === "string" || typeof v === "number");
      if (isPrimitiveArray && value.length > 0) {
        const joined = value.slice(0, 5).join(", ");
        lines.push(`${key}: ${joined}${value.length > 5 ? ` (+${value.length - 5} daha)` : ""}`);
      } else {
        lines.push(`${key}: ${value.length} öğe`);
      }
    } else if (isPlainObject(value)) {
      const subEntries = Object.entries(value);
      const bucketLines = subEntries
        .filter(([, v]) => isPlainObject(v) && ("sample_size" in v || "win_rate" in v))
        .slice(0, 3)
        .map(([subKey, v]) => {
          const sub = v as Record<string, unknown>;
          const n = sub.sample_size ?? sub.votes_cast ?? "?";
          const wr = typeof sub.win_rate === "number" ? `%${(sub.win_rate * 100).toFixed(0)}` : null;
          const acc = typeof sub === "object" && typeof (sub as Record<string, unknown>).brier_score === "number"
            ? `brier=${(sub.brier_score as number).toFixed(3)}`
            : null;
          return `${subKey}(n=${n}${wr ? `, ${wr}` : ""}${acc ? `, ${acc}` : ""})`;
        });
      if (bucketLines.length > 0) {
        lines.push(`${key}: ${bucketLines.join(", ")}`);
      } else {
        // Kullanıcı bulgusu (GPT raporu): self_model'in "inputs" alanı
        // (ece/recent_dsr/kill_switch_active/...) hiçbir sample_size/
        // win_rate alt-alanı taşımadığı için sessizce "5 alt-öğe"ye
        // düşüyordu — gerçek ECE/DSR değerleri hiç görünmüyordu.
        // Primitif alt-değerler artık key=value olarak gösteriliyor.
        const primitiveLines = subEntries
          .filter(([, v]) => v === null || typeof v === "string" || typeof v === "number" || typeof v === "boolean")
          .slice(0, 5)
          .map(([subKey, v]) => `${subKey}=${v === null ? "—" : typeof v === "number" && !Number.isInteger(v) ? v.toFixed(4) : String(v)}`);
        if (primitiveLines.length > 0) {
          lines.push(`${key}: ${primitiveLines.join(", ")}`);
        } else {
          lines.push(`${key}: ${subEntries.length} alt-öğe`);
        }
      }
    }
  }
  return lines.length > 0 ? lines : ["(boş sonuç)"];
}

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
        description="10 Grup B (ölçüm-only) araştırma modülünün hepsini tek seferde, GERÇEK ZAMANLI çalıştırıp özetler — bazı modüller tüm watchlist'i taradığı için tam rapor 1-2 dakika sürebilir. Detaylar kendi sayfalarında kalıyor, buradan doğrudan atlanabilir."
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
                  <ul className="text-xs text-ink-soft font-mono space-y-1">
                    {summarizeResult(m.result).map((line, i) => (
                      <li key={i} className="break-words">{line}</li>
                    ))}
                  </ul>
                )}
              </Card>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
