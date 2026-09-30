const API_ROOT = import.meta.env.VITE_API_URL ?? "";

export class ApiError extends Error {
  constructor(public readonly status: number, message: string) { super(message); this.name = "ApiError"; }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_ROOT}${path}`, { ...init, headers: { "Content-Type": "application/json", ...init?.headers } });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try { const body = await response.json() as { detail?: unknown }; if (body.detail) message = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail); } catch { /* Non-JSON response. */ }
    throw new ApiError(response.status, message);
  }
  return response.json() as Promise<T>;
}

export function errorMessage(error: unknown): string { return error instanceof Error ? error.message : "Unexpected application error"; }
