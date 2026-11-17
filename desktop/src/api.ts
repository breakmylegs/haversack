// The PC host's loopback API (ADR-0039). The token arrives once in the URL fragment, which browsers never
// send to a server; it is kept for this tab only and the fragment is cleared at once.

const TOKEN_KEY = "keepsake-token";

// The launcher may also name the first page to show (``#token=...&page=history``).
const firstPage = /(?:^|&)page=([a-z]{1,20})(?:&|$)/.exec(window.location.hash.slice(1))?.[1] ?? null;

export function initialPage(): string | null {
  return firstPage;
}

function takeToken(): string {
  const match = /(?:^|&)token=([A-Za-z0-9_-]{20,})/.exec(window.location.hash.slice(1));
  if (match) {
    sessionStorage.setItem(TOKEN_KEY, match[1]);
    history.replaceState(null, "", window.location.pathname);
  }
  return sessionStorage.getItem(TOKEN_KEY) ?? "";
}

const token = takeToken();

export class ApiError extends Error {}

export function hasToken(): boolean {
  return token.length > 0;
}

export async function call<T>(name: string, ...args: unknown[]): Promise<T> {
  const response = await fetch(`/api/call/${encodeURIComponent(name)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Keepsake-Token": token },
    body: JSON.stringify({ args }),
    credentials: "omit",
    cache: "no-store",
  });
  let body: { ok: boolean; result?: T; error?: string };
  try {
    body = (await response.json()) as typeof body;
  } catch {
    throw new ApiError(`Keepsake answered ${response.status}`);
  }
  if (!body.ok) throw new ApiError(body.error ?? `Keepsake answered ${response.status}`);
  return body.result as T;
}

export function onEvents(handler: (event: string, args: unknown[]) => void, names: string[]): () => void {
  const source = new EventSource(`/api/events?token=${encodeURIComponent(token)}`);
  const listeners = names.map((name) => {
    const listener = (message: MessageEvent<string>) => {
      try {
        handler(name, JSON.parse(message.data) as unknown[]);
      } catch {
        // a malformed event is ignored
      }
    };
    source.addEventListener(name, listener as EventListener);
    return [name, listener] as const;
  });
  return () => {
    listeners.forEach(([name, listener]) => source.removeEventListener(name, listener as EventListener));
    source.close();
  };
}
