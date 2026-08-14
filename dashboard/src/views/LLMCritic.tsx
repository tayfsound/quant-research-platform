import { useEffect, useState } from "react";
import { authHeaders } from "../api/auth";
import { Card, PageHeader, Button, Badge, ErrorNote, EmptyState, Spinner } from "../components/ui";

// Faz 268-sonrası — kullanıcı isteği: NVIDIA NIM (deepseek-v4-flash)
// tabanlı NvidiaDecisionCritic ile serbest metin soru/cevap sekmesi.
// Gerçek model ~90s'ye kadar sürebiliyor (bkz. llm_reasoner.py'deki A/B
// test notu) — bu kasıtlı bir kalite/hız tercihi, bu yüzden UI bekleme
// süresini açıkça gösteriyor, sessizce donmuş gibi görünmüyor.
//
// Faz 270 — kritik bulgu: LLM'in "kodu ve işlem geçmişini taradım"
// deyip tamamen uydurma sayılar (stop/TP mesafeleri) ürettiği
// yakalandı — hiçbir gerçek DB/kod erişimi yoktu. Artık ask_with_tools()
// gerçek araçlar çağırıyor; her yanıtın altında HANGİ araçları
// çağırdığı şeffaf şekilde gösteriliyor ("uydurmadı, gerçekten baktı"
// güvencesi). Ayrıca LLM artık kod değişikliği önerebiliyor
// (propose_code_change) — bunlar ASLA otomatik uygulanmıyor, aşağıdaki
// öneri kuyruğunda insan onayı bekliyor.
type ToolCall = { tool: string; arguments: Record<string, unknown>; result: unknown };
type ChatMessage = { role: "user" | "assistant"; text: string; toolCalls?: ToolCall[] };

type Proposal = {
  id: string;
  created_at: string;
  title: string;
  file_path: string;
  description: string;
  diff: string;
  rationale: string;
  status: string;
};

function ToolCallTrace({ calls }: { calls: ToolCall[] }) {
  if (calls.length === 0) return null;
  return (
    <details className="mt-2 text-xs">
      <summary className="cursor-pointer text-ink-faint hover:text-ink-soft">
        {calls.length} gerçek araç çağrısı yapıldı — göster
      </summary>
      <div className="mt-1.5 space-y-1.5">
        {calls.map((c, i) => (
          <div key={i} className="bg-canvas border border-line-soft rounded-lg p-2">
            <span className="font-mono text-accent">{c.tool}</span>
            <pre className="whitespace-pre-wrap break-all text-ink-faint mt-1">
              {JSON.stringify(c.result, null, 2).slice(0, 800)}
            </pre>
          </div>
        ))}
      </div>
    </details>
  );
}

function ProposalQueue() {
  const [proposals, setProposals] = useState<Proposal[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = () => {
    fetch("/api/v1/llm-critic/proposals?status=pending", { headers: authHeaders() })
      .then((r) => r.json())
      .then((data) => setProposals(data.proposals || []))
      .catch(() => setProposals([]));
  };

  useEffect(() => {
    load();
    const interval = setInterval(load, 20000);
    return () => clearInterval(interval);
  }, []);

  const decide = (id: string, action: "approve" | "reject") => {
    setError(null);
    setBusyId(id);
    // OPERATOR+ rolü gerektirir — bu asla dosyayı diske yazmaz, sadece
    // durumu değiştirir. Gerçek uygulama daima ayrı bir insan adımı.
    fetch(`/api/v1/llm-critic/proposals/${id}/${action}`, { method: "POST", headers: authHeaders() })
      .then(async (r) => {
        if (!r.ok) {
          const data = await r.json().catch(() => ({}));
          throw new Error(data.detail || `HTTP ${r.status}`);
        }
        setProposals((prev) => prev.filter((p) => p.id !== id));
      })
      .catch((e) => setError(String(e.message || e)))
      .finally(() => setBusyId(null));
  };

  return (
    <div className="mt-8">
      <h3 className="text-sm font-semibold text-ink mb-2">Kod Değişikliği Önerileri</h3>
      <p className="text-xs text-ink-faint mb-3">
        LLM'in önerdiği düzeltmeler — hiçbiri otomatik uygulanmaz, sadece burada onay bekler.
      </p>
      {error && <ErrorNote>{error}</ErrorNote>}
      {proposals.length === 0 ? (
        <EmptyState label="Bekleyen öneri yok." />
      ) : (
        <div className="space-y-4">
          {proposals.map((p) => (
            <Card key={p.id}>
              <div className="flex items-start justify-between gap-4 mb-2">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-ink font-medium">{p.title}</span>
                    <Badge tone="neutral">{p.file_path}</Badge>
                  </div>
                  <p className="text-xs text-ink-faint mt-1">{new Date(p.created_at).toLocaleString()}</p>
                </div>
                <div className="flex gap-2 shrink-0">
                  <Button variant="danger" disabled={busyId === p.id} onClick={() => decide(p.id, "reject")}>
                    Reddet
                  </Button>
                  <Button disabled={busyId === p.id} onClick={() => decide(p.id, "approve")}>
                    Onayla
                  </Button>
                </div>
              </div>
              <p className="text-sm text-ink-soft mb-2">{p.description}</p>
              <p className="text-xs text-ink-faint mb-2">Gerekçe: {p.rationale}</p>
              <pre className="text-xs bg-canvas-soft border border-line-soft rounded-lg p-3 overflow-x-auto whitespace-pre-wrap">
                {p.diff}
              </pre>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

export default function LLMCritic() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const send = () => {
    const message = input.trim();
    if (!message || loading) return;
    setMessages((m) => [...m, { role: "user", text: message }]);
    setInput("");
    setLoading(true);
    setError(null);

    fetch("/api/v1/llm-critic/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ message }),
    })
      .then(async (r) => {
        const data = await r.json();
        if (!r.ok) throw new Error(data.detail || `HTTP ${r.status}`);
        setMessages((m) => [...m, { role: "assistant", text: data.response, toolCalls: data.tool_calls || [] }]);
      })
      .catch((e) => setError(String(e.message || e)))
      .finally(() => setLoading(false));
  };

  return (
    <div>
      <PageHeader
        title="Respond"
        description="NVIDIA NIM (deepseek-v4-flash) — gerçek kod/DB araçlarına erişimi var, sorularını uydurmadan gerçek veriye bakarak cevaplıyor. Yanıt 1-2 dakika sürebilir, bu normal (danışma amaçlı, canlı işlem kapısı değil)."
      />

      {error && <ErrorNote>{error}</ErrorNote>}

      <Card className="mb-3" padded={false}>
        <div className="max-h-[28rem] overflow-y-auto p-5 space-y-4">
          {messages.length === 0 && !loading && (
            <p className="text-sm text-ink-faint">Henüz mesaj yok — aşağıya bir soru yazıp gönder.</p>
          )}
          {messages.map((m, i) => (
            <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
              <div
                className={`max-w-[85%] rounded-xl px-4 py-2.5 text-sm whitespace-pre-wrap ${
                  m.role === "user"
                    ? "bg-accent text-white"
                    : "bg-canvas-soft text-ink border border-line"
                }`}
              >
                {m.text}
                {m.role === "assistant" && m.toolCalls && <ToolCallTrace calls={m.toolCalls} />}
              </div>
            </div>
          ))}
          {loading && (
            <div className="flex justify-start">
              <div className="bg-canvas-soft border border-line rounded-xl px-4 py-2.5 text-sm text-ink-soft flex items-center gap-2">
                <Spinner />
                Yanıt bekleniyor (1-2 dakika sürebilir)…
              </div>
            </div>
          )}
        </div>
      </Card>

      <Card>
        <div className="flex gap-2 items-end">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
            placeholder="Bir soru yaz… (Enter ile gönder, Shift+Enter yeni satır)"
            rows={3}
            className="flex-1 px-3 py-2 rounded-lg bg-canvas-soft border border-line text-sm text-ink placeholder:text-ink-faint focus:outline-none focus:ring-2 focus:ring-accent/30 focus:border-accent resize-none"
          />
          <Button onClick={send} disabled={loading || !input.trim()}>
            {loading ? "Gönderiliyor…" : "Gönder"}
          </Button>
        </div>
      </Card>

      <ProposalQueue />
    </div>
  );
}
