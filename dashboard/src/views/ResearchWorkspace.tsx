import { useEffect, useState } from "react";

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

  const handleUpload = () => {
    fetch("/api/v1/workspace/plugins/upload", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ filename, source_code: sourceCode }),
    })
      .then((r) => r.json())
      .then((data) => {
        if (data.detail) {
          setMessage(`Error: ${data.detail}`);
        } else {
          setMessage(`Uploaded ${data.filename} (hash ${data.hash.slice(0, 12)}...) — review before trusting.`);
          load();
        }
      });
  };

  const handleTrust = (name: string) => {
    fetch(`/api/v1/workspace/plugins/${name}/trust`, { method: "POST" })
      .then((r) => r.json())
      .then((data) => {
        setMessage(`Trusted ${name}. Domains registered: ${data.registered_domains?.join(", ")}`);
        load();
      });
  };

  const handleRevoke = (name: string) => {
    fetch(`/api/v1/workspace/plugins/${name}/revoke`, { method: "POST" }).then(() => load());
  };

  return (
    <div className="p-4 border rounded space-y-4">
      <h2 className="text-lg font-bold">Research Workspace — Agent Plugins</h2>

      <div className="bg-gray-900 p-3 rounded space-y-2">
        <div className="text-sm font-semibold">Upload a new agent (no code change/deploy needed)</div>
        <input
          value={filename}
          onChange={(e) => setFilename(e.target.value)}
          placeholder="my_agent.py"
          className="w-full px-2 py-1 rounded bg-gray-800 text-sm"
        />
        <textarea
          value={sourceCode}
          onChange={(e) => setSourceCode(e.target.value)}
          placeholder="PLUGIN_DOMAIN = AgentDomain.QUANT&#10;PLUGIN_AGENT_CLASS = MyAgent"
          rows={6}
          className="w-full px-2 py-1 rounded bg-gray-800 text-xs font-mono"
        />
        <button onClick={handleUpload} className="px-3 py-1 bg-blue-500 text-white rounded text-sm">
          Upload
        </button>
        {message && <div className="text-xs text-gray-300">{message}</div>}
      </div>

      <div className="space-y-2">
        {plugins.length === 0 ? (
          <div className="text-sm">No plugins uploaded yet</div>
        ) : (
          plugins.map((p) => (
            <div key={p.filename} className="flex justify-between items-center text-sm p-2 bg-gray-50 rounded">
              <div>
                <div>{p.filename}</div>
                <div className="text-xs text-gray-500">hash: {p.hash.slice(0, 16)}...</div>
              </div>
              {p.trusted ? (
                <div className="flex gap-2 items-center">
                  <span className="text-green-500 text-xs">trusted &amp; active</span>
                  <button
                    onClick={() => handleRevoke(p.filename)}
                    className="px-2 py-1 bg-red-600 text-white rounded text-xs"
                  >
                    Revoke
                  </button>
                </div>
              ) : (
                <button
                  onClick={() => handleTrust(p.filename)}
                  className="px-3 py-1 bg-green-600 text-white rounded text-sm"
                >
                  Review &amp; Trust
                </button>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
