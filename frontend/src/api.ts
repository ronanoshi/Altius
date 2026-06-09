const BASE = '';  // proxied via Vite → http://localhost:8000

export async function postLogin(username: string, password: string): Promise<void> {
  const r = await fetch(`${BASE}/api/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });
  if (!r.ok) {
    const body = await r.json().catch(() => ({}));
    throw new Error((body as { detail?: string }).detail ?? 'Login failed');
  }
}

export async function getHoldings() {
  const r = await fetch(`${BASE}/api/holdings`);
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export async function getFiles() {
  const r = await fetch(`${BASE}/api/files`);
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export async function postChat(question: string, nResults = 8) {
  const r = await fetch(`${BASE}/api/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, n_results: nResults }),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export function openFileUrl(fileId: number) {
  return `${BASE}/api/files/${fileId}/open`;
}
