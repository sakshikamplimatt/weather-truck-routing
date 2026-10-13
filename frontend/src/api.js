// All calls go to /api (same origin in production, Vite proxy in dev).
// VITE_API_BASE can point at a separately hosted backend.
const BASE = import.meta.env.VITE_API_BASE || "";

async function request(path, options) {
  const res = await fetch(`${BASE}/api${path}`, options);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
  return data;
}

const post = (path, body, signal) =>
  request(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });

export const geocode = (q, signal) => request(`/geocode?q=${encodeURIComponent(q)}`, { signal });
export const planTrip = (body, signal) => post("/plan", body, signal);
export const fetchHeatmap = (body, signal) => post("/heatmap", body, signal);
