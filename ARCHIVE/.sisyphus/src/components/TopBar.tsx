"use client";

import { useChatStore } from "@/lib/store";
import {
  Cpu,
  Sparkles,
  Zap,
  Users,
  SlidersHorizontal,
  Play,
  Square,
  MoreHorizontal,
} from "lucide-react";
import { useState } from "react";

const MODEL_OPTIONS = [
  { value: "gpt-4o", label: "GPT-4o", provider: "OpenAI" },
  { value: "claude-sonnet-4-20250514", label: "Claude Sonnet 4", provider: "Anthropic" },
  { value: "gemini-2.5-pro", label: "Gemini 2.5 Pro", provider: "Google" },
  { value: "llama-4-maverick", label: "Llama 4 Maverick", provider: "Local" },
];

export function TopBar() {
  const store = useChatStore();
  const {
    activeThreadId,
    threads,
    updateThread,
    streaming,
    cancelStream,
  } = store;

  const activeThread = threads.find((t) => t.id === activeThreadId);
  const [showModelMenu, setShowModelMenu] = useState(false);
  const [showAgentMenu, setShowAgentMenu] = useState(false);

  const currentModel = MODEL_OPTIONS.find(
    (m) => m.value === activeThread?.model,
  ) || MODEL_OPTIONS[0];

  return (
    <header className="flex h-11 items-center gap-1 border-b border-zinc-800 bg-zinc-900 px-3">
      {/* Thread title */}
      <div className="flex-1 min-w-0">
        {activeThread ? (
          <h1 className="truncate text-sm font-medium text-zinc-200">
            {activeThread.title}
          </h1>
        ) : (
          <span className="text-sm text-zinc-500">FlowManner</span>
        )}
      </div>

      {/* Controls */}
      <div className="flex items-center gap-1">
        {/* Model Picker */}
        <div className="relative">
          <button
            onClick={() => {
              setShowModelMenu(!showModelMenu);
              setShowAgentMenu(false);
            }}
            className="flex items-center gap-1 rounded-md px-2 py-1 text-xs text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200 transition-colors"
          >
            <Cpu className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">{currentModel.label}</span>
          </button>
          {showModelMenu && (
            <div className="absolute right-0 top-full z-50 mt-1 w-56 rounded-lg border border-zinc-700 bg-zinc-850 bg-zinc-900 p-1 shadow-xl">
              {MODEL_OPTIONS.map((m) => (
                <button
                  key={m.value}
                  onClick={() => {
                    if (activeThreadId) {
                      updateThread(activeThreadId, {
                        model: m.value,
                        provider: m.provider.toLowerCase() as "openai" | "anthropic" | "google" | "groq" | "together" | "local",
                      });
                    }
                    setShowModelMenu(false);
                  }}
                  className={`flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-xs text-left ${
                    m.value === activeThread?.model
                      ? "bg-blue-600/20 text-blue-400"
                      : "text-zinc-300 hover:bg-zinc-800"
                  }`}
                >
                  <Sparkles className="h-3 w-3" />
                  <div>
                    <div className="font-medium">{m.label}</div>
                    <div className="text-[10px] text-zinc-500">{m.provider}</div>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Agent/Team Picker */}
        <div className="relative">
          <button
            onClick={() => {
              setShowAgentMenu(!showAgentMenu);
              setShowModelMenu(false);
            }}
            className="flex items-center gap-1 rounded-md px-2 py-1 text-xs text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200 transition-colors"
            title="Agent / Team"
          >
            <Users className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">Assistant</span>
          </button>
          {showAgentMenu && (
            <div className="absolute right-0 top-full z-50 mt-1 w-56 rounded-lg border border-zinc-700 bg-zinc-900 p-1 shadow-xl">
              <button className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-xs text-zinc-300 hover:bg-zinc-800">
                <Zap className="h-3 w-3" />
                <div>
                  <div className="font-medium">Assistant</div>
                  <div className="text-[10px] text-zinc-500">
                    Quick chat + tool calls
                  </div>
                </div>
              </button>
              <button className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-xs text-zinc-300 hover:bg-zinc-800">
                <Users className="h-3 w-3" />
                <div>
                  <div className="font-medium">Engineering Team</div>
                  <div className="text-[10px] text-zinc-500">
                    Multi-agent: code + review
                  </div>
                </div>
              </button>
              <button className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-xs text-zinc-300 hover:bg-zinc-800">
                <Users className="h-3 w-3" />
                <div>
                  <div className="font-medium">Marketing Team</div>
                  <div className="text-[10px] text-zinc-500">
                    Content + SEO + analytics
                  </div>
                </div>
              </button>
            </div>
          )}
        </div>

        {/* Settings */}
        <button
          className="rounded-md p-1.5 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-300 transition-colors"
          title="Thread settings"
        >
          <SlidersHorizontal className="h-3.5 w-3.5" />
        </button>

        {/* Run / Stop */}
        <div className="ml-1 flex items-center gap-1 border-l border-zinc-700 pl-2">
          {streaming.isStreaming ? (
            <button
              onClick={cancelStream}
              className="flex items-center gap-1 rounded-md bg-red-600/20 px-2 py-1 text-xs text-red-400 hover:bg-red-600/30 transition-colors"
            >
              <Square className="h-3 w-3" />
              <span className="hidden sm:inline">Stop</span>
            </button>
          ) : (
            <button
              className="flex items-center gap-1 rounded-md bg-blue-600/20 px-2 py-1 text-xs text-blue-400 hover:bg-blue-600/30 transition-colors"
              title="Run agent"
            >
              <Play className="h-3 w-3" />
              <span className="hidden sm:inline">Run</span>
            </button>
          )}
        </div>

        <button className="rounded-md p-1.5 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-300">
          <MoreHorizontal className="h-3.5 w-3.5" />
        </button>
      </div>
    </header>
  );
}
