import type {
  Thread,
  ChatMessage,
  CanvasTile,
  WorkspaceTool,
  AgentTeam,
  Branch,
  Sandbox,
} from "./types";

const BASE = "";

async function fetchJSON<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(
      (body as { error?: string }).error || `HTTP ${res.status}`,
    );
  }
  return res.json();
}

// ── Threads ─────────────────────────────────────────────────────────────

export async function getThreads(workspaceId = "default"): Promise<Thread[]> {
  return fetchJSON<Thread[]>(
    `${BASE}/api/threads?workspaceId=${workspaceId}`,
  );
}

export async function createThread(data: {
  title?: string;
  model?: string;
  provider?: string;
  systemPrompt?: string;
  maxTokens?: number;
  temperature?: number;
  agentTeamId?: string;
}): Promise<Thread> {
  return fetchJSON<Thread>(`${BASE}/api/threads`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export async function getThread(id: string): Promise<Thread> {
  return fetchJSON<Thread>(`${BASE}/api/threads/${id}`);
}

export async function updateThread(
  id: string,
  data: Partial<Thread>,
): Promise<Thread> {
  return fetchJSON<Thread>(`${BASE}/api/threads/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export async function deleteThread(id: string): Promise<void> {
  await fetchJSON<{ success: boolean }>(`${BASE}/api/threads/${id}`, {
    method: "DELETE",
  });
}

// ── Messages ────────────────────────────────────────────────────────────

export async function getMessages(
  threadId: string,
): Promise<ChatMessage[]> {
  return fetchJSON<ChatMessage[]>(
    `${BASE}/api/threads/${threadId}/messages`,
  );
}

export async function createMessage(data: {
  threadId: string;
  role: string;
  content: string;
  parentMessageId?: string;
  branchId?: string;
  steps?: {
    stepType: string;
    status: string;
    name: string;
    displayName?: string;
    args?: unknown;
    result?: unknown;
    agentName?: string;
  }[];
}): Promise<ChatMessage> {
  return fetchJSON<ChatMessage>(`${BASE}/api/threads/${data.threadId}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

// ── Streaming ───────────────────────────────────────────────────────────

export function streamChat(
  body: {
    threadId: string;
    content: string;
    model?: string;
    includeTools?: boolean;
  },
  onEvent: (type: string, data: Record<string, unknown>) => void,
  onError: (error: Error) => void,
  onDone: () => void,
): AbortController {
  const controller = new AbortController();

  fetch(`${BASE}/api/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal: controller.signal,
  })
    .then(async (response) => {
      if (!response.ok) {
        throw new Error(`Stream error: ${response.status}`);
      }

      const reader = response.body?.getReader();
      if (!reader) throw new Error("No reader available");

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        let currentEvent = "";
        for (const line of lines) {
          if (line.startsWith("event: ")) {
            currentEvent = line.slice(7).trim();
          } else if (line.startsWith("data: ")) {
            try {
              const data = JSON.parse(line.slice(6));
              onEvent(currentEvent, data);
            } catch {
              // skip malformed JSON
            }
          }
        }
      }
      onDone();
    })
    .catch((err) => {
      if (err.name !== "AbortError") {
        onError(err instanceof Error ? err : new Error(String(err)));
      }
    });

  return controller;
}

// ── Tools ───────────────────────────────────────────────────────────────

export async function getTools(
  workspaceId = "default",
): Promise<WorkspaceTool[]> {
  return fetchJSON<WorkspaceTool[]>(
    `${BASE}/api/tools?workspaceId=${workspaceId}`,
  );
}

// ── Canvas Tiles ────────────────────────────────────────────────────────

export async function getCanvasTiles(
  threadId: string,
): Promise<CanvasTile[]> {
  return fetchJSON<CanvasTile[]>(
    `${BASE}/api/canvas-tiles?threadId=${threadId}`,
  );
}

export async function createCanvasTile(data: {
  threadId: string;
  tileKind: string;
  title?: string;
  layout?: { x: number; y: number; w: number; h: number };
  config?: unknown;
  sortOrder?: number;
}): Promise<CanvasTile> {
  return fetchJSON<CanvasTile>(`${BASE}/api/canvas-tiles`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export async function updateCanvasTile(
  id: string,
  data: Partial<CanvasTile>,
): Promise<CanvasTile> {
  return fetchJSON<CanvasTile>(`${BASE}/api/canvas-tiles/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export async function deleteCanvasTile(id: string): Promise<void> {
  await fetchJSON<{ success: boolean }>(
    `${BASE}/api/canvas-tiles/${id}`,
    { method: "DELETE" },
  );
}

// ── Agent Teams ─────────────────────────────────────────────────────────

export async function getAgentTeams(): Promise<AgentTeam[]> {
  return fetchJSON<AgentTeam[]>(`${BASE}/api/agent-teams`);
}

// ── Branches ────────────────────────────────────────────────────────────

export async function getBranches(threadId: string): Promise<Branch[]> {
  return fetchJSON<Branch[]>(
    `${BASE}/api/branches?threadId=${threadId}`,
  );
}

export async function createBranch(data: {
  threadId: string;
  parentMessageId: string;
  title?: string;
}): Promise<Branch> {
  return fetchJSON<Branch>(`${BASE}/api/branches`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

// ── Sandboxes ───────────────────────────────────────────────────────────

export async function getSandboxes(
  threadId?: string,
  messageId?: string,
): Promise<Sandbox[]> {
  const params = new URLSearchParams();
  if (threadId) params.set("threadId", threadId);
  if (messageId) params.set("messageId", messageId);
  return fetchJSON<Sandbox[]>(`${BASE}/api/sandboxes?${params}`);
}

export async function createSandbox(data: {
  sandboxType: string;
  language?: string;
  threadId?: string;
  messageId?: string;
  previewUrl?: string;
}): Promise<Sandbox> {
  return fetchJSON<Sandbox>(`${BASE}/api/sandboxes`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}
