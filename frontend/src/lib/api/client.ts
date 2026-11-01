'use client';

// ============================================================================
// API client for the FastAPI backend.
// Replaces the previous Supabase client + Next.js server actions.
// ============================================================================

const TOKEN_KEY = 'lio_token';

export function getApiUrl(): string {
  return process.env.NEXT_PUBLIC_API_URL || 'http://localhost:7200';
}

export function getToken(): string | null {
  if (typeof window === 'undefined') return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  window.localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function parseError(response: Response): Promise<ApiError> {
  let message = `Request failed (${response.status})`;
  try {
    const body = await response.json();
    if (typeof body?.detail === 'string') {
      message = body.detail;
    } else if (Array.isArray(body?.detail) && body.detail[0]?.msg) {
      // FastAPI validation errors
      message = body.detail[0].msg;
    }
  } catch {
    // Non-JSON error body — keep the generic message
  }
  return new ApiError(response.status, message);
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  formData?: FormData;
}

export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  let body: BodyInit | undefined;
  if (options.formData) {
    body = options.formData; // browser sets multipart boundary
  } else if (options.body !== undefined) {
    headers['Content-Type'] = 'application/json';
    body = JSON.stringify(options.body);
  }

  const response = await fetch(`${getApiUrl()}${path}`, {
    method: options.method || (body ? 'POST' : 'GET'),
    headers,
    body,
  });

  if (!response.ok) {
    throw await parseError(response);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

/** Fetch a binary resource (with auth) as an object URL, or null if not found. */
export async function apiFetchObjectUrl(path: string): Promise<string | null> {
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const response = await fetch(`${getApiUrl()}${path}`, { headers });
  if (response.status === 404) return null;
  if (!response.ok) throw await parseError(response);
  return URL.createObjectURL(await response.blob());
}
