import { useEffect, useState } from "react";
import { authHeaders } from "../api/auth";
import { Card, PageHeader, Badge, Button, EmptyState } from "../components/ui";

export default function ResearchWorkspace() {
  const [plugins, setPlugins] = useState<any[]>([]);
  const [filename, setFilename] = useState("");
  const [sourceCode, setSourceCode] = useState("");
  const [message, setMessage] = useState<string | null>(null);

  const load = () => {
    fetch("/api/v1/workspace/plugins")
      .then((r) => r.json())
      .then((data) => setPlugins(data.plugins || []));
  };

  useEffect(() => {
    load();
  }, []);

  // Upload/trust/revoke require ADMIN (Sprint 22-24) — loading and running
  // arbitrary code is the highest-sensitivity action in the whole system.
  const handleUpload = () => {
    fetch("/api/v1/workspace/plugins/upload", {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ filename, source_code: sourceCode }),
    })
      .then((r) => r.json())
      .then((data) => {
        if (data.detail) {
          setMessage(`Error: ${data.detail}`);
        } else {
          setMessage(`Uploaded ${data.filename} (hash ${data.hash.slice(0, 12)}…) — review before trusting.`);
          load();
        }
      });
  };

  const handleTrust = (name: string) => {
    fetch(`/api/v1/workspace/plugins/${name}/trust`, { method: "POST", headers: authHeaders() })
      .then((r) => r.json())
      .then((data) => {
        setMessage(`Trusted ${name}. Domains registered: ${data.registered_domains?.join(", ")}`);
        load();
      });
  };

  const handleRevoke = (name: string) => {
    fetch(`/api/v1/workspace/plugins/${name}/revoke`, { method: "POST", headers: authHeaders() }).then(() => load());
  };

  return (
    <div>
      <PageHeader title="Workspace" description="Kod değişikliği/deploy gerektirmeden yeni bir agent plugin'i yükleyip güvenilir kılın." />

      <Card className="mb-6">
        <div className="text-sm font-semibold text-ink mb-3">Upload a new agent</div>
        <div className="space-y-2">
          <input
            value={filename}
            onChange={(e) => setFilename(e.target.value)}
            placeholder="my_agent.py"
            className="w-full px-3 py-2 rounded-lg bg-canvas-soft border border-line text-sm text-ink placeholder:text-ink-faint focus:outline-none focus:ring-2 focus:ring-accent/30"
          />
          <textarea
            value={sourceCode}
            onChange={(e) => setSourceCode(e.target.value)}
            placeholder={"PLUGIN_DOMAIN = AgentDomain.QUANT\nPLUGIN_AGENT_CLASS = MyAgent"}
            rows={6}
            className="w-full px-3 py-2 rounded-lg bg-canvas-soft border border-line text-xs font-mono text-ink placeholder:text-ink-faint focus:outline-none focus:ring-2 focus:ring-accent/30"
          />
          <Button onClick={handleUpload}>Upload</Button>
          {message && <div className="text-xs text-ink-soft mt-1">{message}</div>}
        </div>
      </Card>

      {plugins.length === 0 ? (
        <EmptyState label="Henüz plugin yüklenmedi." />
      ) : (
        <div className="space-y-2">
          {plugins.map((p) => (
            <Card key={p.filename} className="flex justify-between items-center">
              <div>
                <div className="text-sm font-medium text-ink">{p.filename}</div>
                <div className="text-xs text-ink-faint mt-0.5 font-mono">{p.hash.slice(0, 16)}…</div>
              </div>
              {p.trusted ? (
                <div className="flex gap-3 items-center">
                  <Badge tone="rise">trusted &amp; active</Badge>
                  <Button variant="danger" onClick={() => handleRevoke(p.filename)}>Revoke</Button>
                </div>
              ) : (
                <Button variant="secondary" onClick={() => handleTrust(p.filename)}>Review &amp; Trust</Button>
              )}
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
