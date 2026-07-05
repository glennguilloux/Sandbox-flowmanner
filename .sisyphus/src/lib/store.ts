"use client";

import { create } from "zustand";
import type {
  Thread,
  ChatMessage,
  CanvasTile,
  WorkspaceTool,
  StreamingState,
  TileLayout,
  SSEEventType,
  ToolCallStart,
  ToolCallResult,
  AgentStepEvent,
  PermissionRequest,
} from "./types";
import * as api from "./api";

// ── Streaming Helpers ───────────────────────────────────────────────────

function createInitialStreamingState(): StreamingState {
  return {
    isStreaming: false,
    content: "",
    reasoning: "",
    activeToolCalls: new Map(),
    toolResults: new Map(),
    activeSteps: new Map(),
    citations: [],
    pendingPermissions: [],
    sandboxEvents: [],
    error: null,
    messageId: null,
  };
}

// ── Store ───────────────────────────────────────────────────────────────

export interface ChatStore {
  // Threads
  threads: Thread[];
  activeThreadId: string | null;
  threadsLoading: boolean;

  // Messages
  messages: ChatMessage[];
  messagesLoading: boolean;

  // Streaming
  streaming: StreamingState;
  streamAbortController: AbortController | null;

  // Canvas
  tiles: CanvasTile[];
  tilesLoading: boolean;

  // Tools
  tools: WorkspaceTool[];
  toolsLoading: boolean;

  // UI State
  isZenMode: boolean;
  isMobileSidebarOpen: boolean;
  isRightSidebarOpen: boolean;
  sandboxPanelExpanded: boolean;

  // Actions — Threads
  fetchThreads: () => Promise<void>;
  createThread: (data?: {
    title?: string;
    model?: string;
    agentTeamId?: string;
  }) => Promise<Thread>;
  setActiveThread: (id: string) => void;
  updateThread: (id: string, data: Partial<Thread>) => Promise<void>;
  deleteThread: (id: string) => Promise<void>;

  // Actions — Messages
  fetchMessages: (threadId: string) => Promise<void>;
  sendMessage: (content: string) => Promise<void>;
  cancelStream: () => void;
  addMessage: (msg: ChatMessage) => void;

  // Actions — Streaming event handlers
  handleSSEEvent: (type: SSEEventType, data: Record<string, unknown>) => void;
  finalizeStream: () => void;

  // Actions — Canvas
  fetchTiles: (threadId: string) => Promise<void>;
  addTile: (tile: {
    threadId: string;
    tileKind: string;
    title?: string;
    layout?: TileLayout;
  }) => Promise<void>;
  updateTileLayout: (id: string, layout: TileLayout) => Promise<void>;
  removeTile: (id: string) => Promise<void>;

  // Actions — Tools
  fetchTools: () => Promise<void>;

  // Actions — UI
  toggleZenMode: () => void;
  toggleMobileSidebar: () => void;
  toggleRightSidebar: () => void;
  toggleSandboxPanel: () => void;
}

export const useChatStore = create<ChatStore>((set, get) => ({
  // ── Initial State ───────────────────────────────────────────────────

  threads: [],
  activeThreadId: null,
  threadsLoading: false,

  messages: [],
  messagesLoading: false,

  streaming: createInitialStreamingState(),
  streamAbortController: null,

  tiles: [],
  tilesLoading: false,

  tools: [],
  toolsLoading: false,

  isZenMode: false,
  isMobileSidebarOpen: false,
  isRightSidebarOpen: true,
  sandboxPanelExpanded: false,

  // ── Thread Actions ──────────────────────────────────────────────────

  fetchThreads: async () => {
    set({ threadsLoading: true });
    try {
      const threads = await api.getThreads();
      set({ threads });
    } catch (e) {
      console.error("Failed to fetch threads:", e);
    } finally {
      set({ threadsLoading: false });
    }
  },

  createThread: async (data) => {
    const thread = await api.createThread({
      title: data?.title || "New Chat",
      model: data?.model || "gpt-4o",
      agentTeamId: data?.agentTeamId,
    });
    set((s) => ({
      threads: [thread, ...s.threads],
      activeThreadId: thread.id,
      messages: [],
      tiles: [],
    }));
    return thread;
  },

  setActiveThread: (id) => {
    set({ activeThreadId: id, messages: [], tiles: [], streaming: createInitialStreamingState() });
  },

  updateThread: async (id, data) => {
    const updated = await api.updateThread(id, data);
    set((s) => ({
      threads: s.threads.map((t) => (t.id === id ? updated : t)),
    }));
  },

  deleteThread: async (id) => {
    await api.deleteThread(id);
    set((s) => ({
      threads: s.threads.filter((t) => t.id !== id),
      activeThreadId:
        s.activeThreadId === id ? null : s.activeThreadId,
      messages: s.activeThreadId === id ? [] : s.messages,
    }));
  },

  // ── Message Actions ─────────────────────────────────────────────────

  fetchMessages: async (threadId) => {
    set({ messagesLoading: true });
    try {
      const messages = await api.getMessages(threadId);
      set({ messages });
    } catch (e) {
      console.error("Failed to fetch messages:", e);
    } finally {
      set({ messagesLoading: false });
    }
  },

  sendMessage: async (content) => {
    const state = get();
    let threadId = state.activeThreadId;

    // Create a thread if none active
    if (!threadId) {
      const thread = await state.createThread({
        title: content.slice(0, 60) || "New Chat",
      });
      threadId = thread.id;
    }

    // Add user message
    const userMsg: ChatMessage = {
      id: crypto.randomUUID(),
      threadId,
      role: "user",
      content,
      steps: [],
      parentMessageId: null,
      branchId: null,
      sandboxId: null,
      tokenCount: null,
      cost: null,
      isEdited: false,
      isRegenerated: false,
      reasoning: null,
      citations: null,
      createdAt: new Date(),
    };

    set((s) => ({
      messages: [...s.messages, userMsg],
      streaming: {
        ...createInitialStreamingState(),
        isStreaming: true,
      },
    }));

    // Persist user message
    try {
      await api.createMessage({
        threadId,
        role: "user",
        content,
      });
    } catch (e) {
      console.error("Failed to persist user message:", e);
    }

    // Start SSE stream
    const controller = api.streamChat(
      {
        threadId,
        content,
        model: state.threads.find((t) => t.id === threadId)?.model,
        includeTools: true,
      },
      (type, data) => {
        get().handleSSEEvent(type as SSEEventType, data);
      },
      (error) => {
        console.error("Stream error:", error);
        set((s) => ({
          streaming: { ...s.streaming, error: error.message, isStreaming: false },
        }));
      },
      () => {
        get().finalizeStream();
      },
    );

    set({ streamAbortController: controller });
  },

  cancelStream: () => {
    const { streamAbortController } = get();
    if (streamAbortController) {
      streamAbortController.abort();
    }
    set((s) => ({
      streaming: { ...s.streaming, isStreaming: false },
      streamAbortController: null,
    }));
  },

  addMessage: (msg) => {
    set((s) => ({ messages: [...s.messages, msg] }));
  },

  // ── SSE Event Handler ───────────────────────────────────────────────

  handleSSEEvent: (type, data) => {
    set((s) => {
      const st = { ...s.streaming };

      switch (type) {
        case "text_delta":
          st.content += (data.content as string) || "";
          break;

        case "reasoning_delta":
          st.reasoning += (data.content as string) || "";
          break;

        case "tool_call_start": {
          const tc = data as unknown as ToolCallStart;
          st.activeToolCalls = new Map(s.streaming.activeToolCalls);
          st.activeToolCalls.set(tc.toolCallId, tc);
          break;
        }

        case "tool_call_result": {
          const tr = data as unknown as ToolCallResult;
          st.toolResults = new Map(s.streaming.toolResults);
          st.toolResults.set(tr.toolCallId, tr);
          st.activeToolCalls = new Map(s.streaming.activeToolCalls);
          st.activeToolCalls.delete(tr.toolCallId);
          break;
        }

        case "agent_step_start": {
          const step = data as unknown as AgentStepEvent;
          st.activeSteps = new Map(s.streaming.activeSteps);
          st.activeSteps.set(step.stepId, step);
          break;
        }

        case "agent_step_end": {
          st.activeSteps = new Map(s.streaming.activeSteps);
          st.activeSteps.delete(data.stepId as string);
          break;
        }

        case "citation":
          st.citations = [
            ...s.streaming.citations,
            ...((data as { sources: typeof s.streaming.citations }).sources || []),
          ];
          break;

        case "permission_request":
          st.pendingPermissions = [
            ...s.streaming.pendingPermissions,
            data as unknown as PermissionRequest,
          ];
          break;

        case "canvas_update":
          // Canvas updates are handled separately
          break;

        case "sandbox_event":
          st.sandboxEvents = [
            ...s.streaming.sandboxEvents,
            data as unknown as { sandboxId: string; status: string; previewUrl?: string },
          ];
          break;

        case "error":
          st.error = (data.message as string) || "Unknown error";
          st.isStreaming = false;
          break;

        case "done":
          st.messageId = data.messageId as string;
          break;
      }

      return { streaming: st };
    });
  },

  finalizeStream: () => {
    const state = get();
    const { streaming, activeThreadId } = state;

    if (!activeThreadId) return;

    const assistantMsg: ChatMessage = {
      id: streaming.messageId || crypto.randomUUID(),
      threadId: activeThreadId,
      role: "assistant",
      content: streaming.content,
      reasoning: streaming.reasoning || null,
      citations: streaming.citations.length > 0 ? streaming.citations : null,
      steps: Array.from(streaming.toolResults.entries()).map(([id, tr]) => ({
        id: crypto.randomUUID(),
        messageId: streaming.messageId || "",
        stepType: "tool" as const,
        status: tr.status === "completed" ? "completed" as const : "failed" as const,
        name: tr.toolName,
        displayName: tr.toolName,
        args: {} as Record<string, unknown>,
        result: tr.result as Record<string, unknown>,
        error: null,
        agentName: "assistant",
        capabilityToken: null,
        toolCallId: id,
        startedAt: null,
        endedAt: new Date(),
        createdAt: new Date(),
      })),
      parentMessageId: null,
      branchId: null,
      sandboxId: null,
      tokenCount: null,
      cost: null,
      isEdited: false,
      isRegenerated: false,
      createdAt: new Date(),
    };

    // Persist the assistant message
    api
      .createMessage({
        threadId: activeThreadId,
        role: "assistant",
        content: streaming.content,
      })
      .catch((e) => console.error("Failed to persist assistant message:", e));

    set((s) => ({
      messages: [...s.messages, assistantMsg],
      streaming: createInitialStreamingState(),
      streamAbortController: null,
    }));
  },

  // ── Canvas Actions ──────────────────────────────────────────────────

  fetchTiles: async (threadId) => {
    set({ tilesLoading: true });
    try {
      const tiles = await api.getCanvasTiles(threadId);
      set({ tiles });
    } catch (e) {
      console.error("Failed to fetch tiles:", e);
    } finally {
      set({ tilesLoading: false });
    }
  },

  addTile: async (data) => {
    const tile = await api.createCanvasTile(data);
    set((s) => ({ tiles: [...s.tiles, tile] }));
  },

  updateTileLayout: async (id, layout) => {
    // Optimistic update
    set((s) => ({
      tiles: s.tiles.map((t) =>
        t.id === id ? { ...t, layout } : t,
      ),
    }));
    try {
      await api.updateCanvasTile(id, { layout } as Partial<CanvasTile>);
    } catch (e) {
      console.error("Failed to update tile layout:", e);
    }
  },

  removeTile: async (id) => {
    set((s) => ({ tiles: s.tiles.filter((t) => t.id !== id) }));
    try {
      await api.deleteCanvasTile(id);
    } catch (e) {
      console.error("Failed to delete tile:", e);
    }
  },

  // ── Tool Actions ────────────────────────────────────────────────────

  fetchTools: async () => {
    set({ toolsLoading: true });
    try {
      const tools = await api.getTools();
      set({ tools });
    } catch (e) {
      console.error("Failed to fetch tools:", e);
    } finally {
      set({ toolsLoading: false });
    }
  },

  // ── UI Actions ──────────────────────────────────────────────────────

  toggleZenMode: () => set((s) => ({ isZenMode: !s.isZenMode })),
  toggleMobileSidebar: () =>
    set((s) => ({ isMobileSidebarOpen: !s.isMobileSidebarOpen })),
  toggleRightSidebar: () =>
    set((s) => ({ isRightSidebarOpen: !s.isRightSidebarOpen })),
  toggleSandboxPanel: () =>
    set((s) => ({ sandboxPanelExpanded: !s.sandboxPanelExpanded })),
}));
