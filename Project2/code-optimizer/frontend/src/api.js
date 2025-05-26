// src/api.js
const API = import.meta.env.VITE_API_URL || "/api";  // Use environment variable with fallback

function fetchOpts(method, body) {
  const opts = { method, credentials: "include" };
  if (body) {
    opts.headers = { "Content-Type": "application/json" };
    opts.body    = JSON.stringify(body);
  }
  return opts;
}

export async function createSession() {
  const res = await fetch(`${API}/session`, fetchOpts("POST"));
  if (!res.ok) throw new Error("session failed");
}

export async function cloneRepo(url) {
  const res = await fetch(`${API}/clone`, fetchOpts("POST", { repo_url: url }));
  if (!res.ok) throw new Error(`clone failed (${res.status})`);
  return res.json();
}

export async function getFile(path) {
  const res = await fetch(
    `${API}/file?relative_path=${encodeURIComponent(path)}`,
    fetchOpts("GET")
  );
  if (!res.ok) throw new Error(`getFile failed (${res.status})`);
  return res.text();
}

export async function optimise(code, feedback) {
  const res = await fetch(
    `${API}/optimise`,
    fetchOpts("POST", { code, feedback })
  );
  if (!res.ok) throw new Error(`optimise failed (${res.status})`);
  return res.json();
}


// Simple health check function
export async function checkHealth() {
  try {
    const res = await fetch(`${API}/health`, fetchOpts("GET"));
    return res.ok;
  } catch (error) {
    console.error("Health check failed:", error);
    return false;
  }
}

export async function checkConnection() {
  try {
    // First try health endpoint
    const isHealthy = await checkHealth();
    if (isHealthy) return true;
    
    // If health check fails, try creating a session
    await createSession();
    return true;
  } catch (error) {
    console.error("Connection check failed:", error);
    return false;
  }}