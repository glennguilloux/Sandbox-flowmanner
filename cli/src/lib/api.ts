/**
 * Thin fetch wrapper around the FlowManner v2 API.
 *
 * Responsibilities:
 * - Attach `Authorization: Bearer *** from saved credentials
 * - Unwrap the v2 envelope (`{ data, meta, error }`) so callers see just the payload
 * - Surface v2 error envelopes as FlowmannerApiError with code/message/details
 * - Provide streaming variants for SSE endpoints (events, mission stream)
 *
 * All v2 endpoints use standardized envelopes — see
 * backend/app/api/v2/base.py. Non-2xx responses carry
 * `{ data: null, error: { code, message, details }, meta }`.
 */
import { getBaseUrl, loadCredentials } from "./config.js";

export interface ApiErrorBody {
  code: string;
  message: string;
  details?: Record<string, unknown>;
}

export class FlowmannerApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly details?: Record<string, unknown>;

  constructor(status: number, body: ApiErrorBody) {
    super(`${body.code}: ${body.message}`);
    this.name = "FlowmannerApiError";
    this.status = status;
    this.code = body.code;
    this.details = body.details;
  }
}

export class NotAuthenticatedError extends Error {
  constructor() {
    super("Not logged in. Run `flowmanner login` first.");
    this.name = "NotAuthenticatedError";
  }
}

interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  body?: unknown;
  query?: Record<string, string | number | boolean | undefined>;
  /** When true, attach JWT. Default true. */
  auth?: boolean;
}

function buildUrl(
  baseUrl: string,
  path: string,
  query?: RequestOptions["query"],
): string {
  const url = new URL(path.replace(/^\//, ""), `${baseUrl}/`);
  if (query) {
    for (const [k, v] of Object.entries(query)) {
      if (v !== undefined) url.searchParams.set(k, String(v));
    }
  }
  return url.toString();
}

export async function apiRequest<T = unknown>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const { method = "GET", body, query, auth = true } = options;
  const baseUrl = getBaseUrl();

  const headers: Record<string, string> = {
    Accept: "application/json",
    "X-Client": "flowmanner-cli@0.1.0",
  };
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
  }
  if (auth) {
    const creds = loadCredentials();
    if (!creds) throw new NotAuthenticatedError();
    headers["Authorization"] = `Bearer ${creds.token}`;
  }

  const response = await fetch(buildUrl(baseUrl, path, query), {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  // 204 No Content (DELETE responses, logout)
  if (response.status === 204) return undefined as T;

  // Try to parse JSON — some endpoints (health) return plain JSON
  // without an envelope, so we accept either shape.
  let payload: unknown = null;
  const text = await response.text();
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      // Non-JSON body — surface as a generic error.
      if (!response.ok) {
        throw new FlowmannerApiError(response.status, {
          code: "HTTP_ERROR",
          message: text.slice(0, 500) || `HTTP ${response.status}`,
        });
      }
      return text as unknown as T;
    }
  }

  if (!response.ok) {
    const envelope = payload as
      | { data: null; error: ApiErrorBody; meta?: unknown }
      | null;
    const errBody =
      envelope?.error ??
      ({
        code: "HTTP_ERROR",
        message: `Request failed with status ${response.status}`,
      } satisfies ApiErrorBody);
    throw new FlowmannerApiError(response.status, errBody);
  }

  // Unwrap v2 envelope if present. If the response has no `data`
  // field, return it as-is (e.g. plain /api/health responses).
  if (
    payload &&
    typeof payload === "object" &&
    "data" in (payload as Record<string, unknown>)
  ) {
    return (payload as { data: T }).data;
  }
  return payload as T;
}

/**
 * Open an SSE stream and yield parsed events.
 *
 * Backed by fetch + ReadableStream — no extra dependency. Closes the
 * stream when the caller breaks out of the for-await loop.
 *
 * Endpoint convention: each `data:` line is a JSON object. A literal
 * `data: [DONE]` terminates the stream.
 */
export async function* sseStream(
  path: string,
  options: { query?: RequestOptions["query"] } = {},
): AsyncGenerator<{ event: string; data: unknown }> {
  const baseUrl = getBaseUrl();
  const creds = loadCredentials();
  if (!creds) throw new NotAuthenticatedError();

  const headers: Record<string, string> = {
    Accept: "text/event-stream",
    Authorization: `Bearer ${creds.token}`,
    "X-Client": "flowmanner-cli@0.1.0",
  };

  const response = await fetch(buildUrl(baseUrl, path, options.query), {
    headers,
  });
  if (!response.ok || !response.body) {
    throw new FlowmannerApiError(response.status, {
      code: "SSE_CONNECT_FAILED",
      message: `Failed to open SSE stream: ${response.status}`,
    });
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      // SSE messages are separated by a blank line (\n\n).
      let sepIdx = buffer.indexOf("\n\n");
      while (sepIdx !== -1) {
        const raw = buffer.slice(0, sepIdx);
        buffer = buffer.slice(sepIdx + 2);
        const parsed = parseSseMessage(raw);
        if (parsed) {
          if (parsed.data === "[DONE]") return;
          yield parsed;
        }
        sepIdx = buffer.indexOf("\n\n");
      }
    }
  } finally {
    reader.releaseLock();
  }
}

function parseSseMessage(
  raw: string,
): { event: string; data: unknown } | null {
  let event = "message";
  const dataLines: string[] = [];
  for (const line of raw.split("\n")) {
    if (line.startsWith(":")) continue; // comment / keepalive
    if (line.startsWith("event:")) {
      event = line.slice(6).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trim());
    }
  }
  if (dataLines.length === 0) return null;
  const dataStr = dataLines.join("\n");
  let data: unknown = dataStr;
  if (dataStr.startsWith("{")) {
    try {
      data = JSON.parse(dataStr);
    } catch {
      // leave as raw string
    }
  }
  return { event, data };
}