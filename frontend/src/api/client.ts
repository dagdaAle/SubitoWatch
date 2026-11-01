export async function request<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const response = await fetch(path, { method, cache: 'no-store', headers: { 'Content-Type': 'application/json' },
    ...(body !== undefined ? { body: JSON.stringify(body) } : {}) });
  if (!response.ok) {
    let message = `Richiesta non riuscita (${response.status})`;
    try { const error = await response.json(); message = typeof error.detail === 'string' ? error.detail : 'Controlla i campi inseriti.'; } catch { /* retain status */ }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}
