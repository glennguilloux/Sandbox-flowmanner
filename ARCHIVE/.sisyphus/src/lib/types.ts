import type {
  Thread,
  Message,
  AgentStep,
  CanvasTile,
  ToolDefinition,
  Sandbox,
  AgentTeam,
  Branch,
} from "@/db/schema";

// ── SSE Event Types ──────────────────────────────────────────────────────

export type SSEEventType =
  | "text_delta"
  | "tool_call_start"
  | "tool_call_delta"
  | "tool_call_result"
  | "agent_step_start"
  | "agent_step_end"
  | "reasoning_delta"
  | "citation"
  | "permission_request"
  | "canvas_update"
  | "sandbox_event"
  | "handoff"
  | "error"
  | "done";

export interface SSEEvent {
  type: SSEEventType;
  data: Record<string, unknown>;
}

export interface ToolCallStart {
  toolCallId: string;
  toolName: string;
  args: Record<string, unknown>;
  timestamp: number;
}

export interface ToolCallResult {
  toolCallId: string;
  toolName: string;
  result: unknown;
  status: "completed" | "failed";
  timestamp: number;
}

export interface AgentStepEvent {
  stepId: string;
  stepType: "tool" | "reasoning" | "handoff" | "sandbox" | "permission";
  status: "pending" | "running" | "completed" | "failed" | "awaiting_approval" | "cancelled";
  agentName: string;
  name: string;
  displayName?: string;
  timestamp: number;
}

export interface PermissionRequest {
  requestId: string;
  toolName: string;
  args: Record<string, unknown>;
  reason: string;
  scope: string;
  timestamp: number;
}

// ── Canvas Types ─────────────────────────────────────────────────────────

export type TileKind =
  | "chat"
  | "code_sandbox"
  | "browser_sandbox"
  | "agent_reasoning"
  | "file_diff"
  | "image_gen"
  | "mission_status";

export interface TileLayout {
  x: number;
  y: number;
  w: number;
  h: number;
  minW?: number;
  minH?: number;
  maxW?: number;
  maxH?: number;
}

// ── Streaming State ─────────────────────────────────────────────────────

export interface StreamingState {
  isStreaming: boolean;
  content: string;
  reasoning: string;
  activeToolCalls: Map<string, ToolCallStart>;
  toolResults: Map<string, ToolCallResult>;
  activeSteps: Map<string, AgentStepEvent>;
  citations: { source: string; excerpt: string; score: number }[];
  pendingPermissions: PermissionRequest[];
  sandboxEvents: { sandboxId: string; status: string; previewUrl?: string }[];
  error: string | null;
  messageId: string | null;
}

// ── Chat Types ──────────────────────────────────────────────────────────

export interface ChatMessage extends Message {
  steps: AgentStep[];
  isStreaming?: boolean;
}

// ── Workspace Types ─────────────────────────────────────────────────────

export interface WorkspaceTool extends ToolDefinition {
  isAllowed: boolean;
}

// ── Re-exports for convenience ──────────────────────────────────────────

export type {
  Thread,
  Message,
  AgentStep,
  CanvasTile,
  ToolDefinition,
  Sandbox,
  AgentTeam,
  Branch,
};
