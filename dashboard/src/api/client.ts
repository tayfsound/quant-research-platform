// Minimal API client -- P2-15
const API_BASE = import.meta.env.VITE_API_URL || "";

export async function fetchLatestCycle() {
  const res = await fetch(`${API_BASE}/api/v1/dashboard/latest`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function fetchHealth() {
  const res = await fetch(`${API_BASE}/health`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}
