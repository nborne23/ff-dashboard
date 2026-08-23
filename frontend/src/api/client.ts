// Minimal typed fetch wrapper for the GridIron backend (FastAPI on :8000,
// proxied through Vite at /api — see vite.config.ts). Every non-2xx response
// is normalized into an ApiError carrying the HTTP status and the parsed
// response body so callers can branch on FastAPI's `detail` shapes:
//   - typed errors:       { detail: { code, message } }
//   - pydantic validation: { detail: [{ loc, msg, type, ... }, ...] }

export class ApiError extends Error {
  readonly status: number;
  readonly body: unknown;

  constructor(status: number, body: unknown) {
    super(`Request failed with status ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

async function parseBody(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) return undefined;
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      ...init.headers,
    },
  });

  const body = await parseBody(response);

  if (!response.ok) {
    throw new ApiError(response.status, body);
  }

  return body as T;
}

export const apiClient = {
  get: <T>(path: string): Promise<T> => request<T>(path),
  post: <T>(path: string, body?: unknown): Promise<T> =>
    request<T>(path, {
      method: "POST",
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
  patch: <T>(path: string, body?: unknown): Promise<T> =>
    request<T>(path, {
      method: "PATCH",
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
  put: <T>(path: string, body?: unknown): Promise<T> =>
    request<T>(path, {
      method: "PUT",
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
  delete: <T = void>(path: string): Promise<T> => request<T>(path, { method: "DELETE" }),
};

interface TypedErrorDetail {
  code?: string;
  message?: string;
}

interface ValidationErrorDetail {
  msg?: string;
}

/** Best-effort extraction of a human-readable message from an ApiError. */
export function getApiErrorMessage(error: unknown, fallback = "Something went wrong."): string {
  if (!(error instanceof ApiError)) return fallback;

  const body = error.body as { detail?: unknown } | undefined;
  const detail = body?.detail;

  if (typeof detail === "string") return detail;

  if (detail && typeof detail === "object" && !Array.isArray(detail)) {
    const message = (detail as TypedErrorDetail).message;
    if (typeof message === "string") return message;
  }

  if (Array.isArray(detail) && detail.length > 0) {
    const message = (detail[0] as ValidationErrorDetail | undefined)?.msg;
    if (typeof message === "string") return message;
  }

  return fallback;
}
