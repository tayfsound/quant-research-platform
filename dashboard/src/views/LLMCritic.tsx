import { useState } from "react";
import { authHeaders } from "../api/auth";
import { Card, PageHeader, Button, ErrorNote, Spinner } from "../components/ui";

// Faz 268-sonrası — kullanıcı isteği: NVIDIA NIM (deepseek-v4-flash)
// tabanlı NvidiaDecisionCritic ile serbest metin soru/cevap sekmesi.
// Gerçek model ~90s'ye kadar sürebiliyor (bkz. llm_reasoner.py'deki A/B
// test notu) — bu kasıtlı bir kalite/hız tercihi, bu yüzden UI bekleme
// süresini açıkça gösteriyor, sessizce donmuş gibi görünmüyor.
type ChatMessage = { role: "user" | "assistant"; text: string };

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
        setMessages((m) => [...m, { role: "assistant", text: data.response }]);
      })
      .catch((e) => setError(String(e.message || e)))
      .finally(() => setLoading(false));
  };

  return (
    <div>
      <PageHeader
        title="Respond"
        description="NVIDIA NIM (deepseek-v4-flash) — serbest soru/cevap. Yanıt 1-2 dakika sürebilir, bu normal (danışma amaçlı, canlı işlem kapısı değil)."
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
    </div>
  );
}
