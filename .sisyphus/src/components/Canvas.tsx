"use client";

import { useChatStore } from "@/lib/store";
import { MessageList } from "./MessageList";
import { SandboxTile } from "./SandboxTile";
import { AgentReasoningTile } from "./AgentReasoningTile";
import { StreamingIndicator } from "./StreamingIndicator";
import {
  Code2,
  Globe,
  Brain,
  FileDiff,
  ImageIcon,
  Target,
  GripHorizontal,
  X,
  Minimize2,
  Maximize2,
} from "lucide-react";
import { useState, useCallback } from "react";

type TileConfig = {
  kind: string;
  title: string;
  icon: React.ReactNode;
  minimized?: boolean;
};

export function Canvas() {
  const store = useChatStore();
  const { messages, streaming, tiles, activeThreadId, removeTile, updateTileLayout } = store;

  const [customTiles, setCustomTiles] = useState<TileConfig[]>([]);

  const toggleTileMinimize = useCallback((index: number) => {
    setCustomTiles((prev) =>
      prev.map((t, i) =>
        i === index ? { ...t, minimized: !t.minimized } : t,
      ),
    );
  }, []);

  const addCustomTile = useCallback((kind: string, title: string, icon: React.ReactNode) => {
    setCustomTiles((prev) => {
      // Don't add duplicate
      if (prev.some((t) => t.kind === kind)) return prev;
      return [...prev, { kind, title, icon }];
    });
  }, []);

  const removeCustomTile = useCallback((index: number) => {
    setCustomTiles((prev) => prev.filter((_, i) => i !== index));
  }, []);

  // Determine active tiles
  const hasSandbox = streaming.sandboxEvents.length > 0;
  const hasAgentSteps = streaming.activeSteps.size > 0;

  if (!activeThreadId && messages.length === 0) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <div className="text-center">
          <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-zinc-800/50">
            <Brain className="h-8 w-8 text-zinc-600" />
          </div>
          <h2 className="text-lg font-medium text-zinc-300">
            FlowManner
          </h2>
          <p className="mt-1 max-w-md text-sm text-zinc-500">
            Hybrid chat + tools + agents + sandbox — all in one canvas.
            Start a new thread or pick one from the sidebar.
          </p>
          <div className="mt-6 flex flex-wrap justify-center gap-2">
            <QuickAction
              icon={<Code2 className="h-4 w-4" />}
              label="Code Sandbox"
              onClick={() => addCustomTile("code_sandbox", "Code Sandbox", <Code2 className="h-4 w-4" />)}
            />
            <QuickAction
              icon={<Globe className="h-4 w-4" />}
              label="Browser"
              onClick={() => addCustomTile("browser_sandbox", "Browser", <Globe className="h-4 w-4" />)}
            />
            <QuickAction
              icon={<Brain className="h-4 w-4" />}
              label="Reasoning"
              onClick={() => addCustomTile("agent_reasoning", "Agent Reasoning", <Brain className="h-4 w-4" />)}
            />
            <QuickAction
              icon={<FileDiff className="h-4 w-4" />}
              label="Files"
              onClick={() => addCustomTile("file_diff", "Files", <FileDiff className="h-4 w-4" />)}
            />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      {/* Canvas grid area */}
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-4xl space-y-4 p-4">
          {/* Chat tile — always present */}
          <div className="rounded-xl border border-zinc-800 bg-zinc-900/50">
            <div className="flex items-center justify-between border-b border-zinc-800 px-4 py-2">
              <span className="text-xs font-medium text-zinc-500">Chat</span>
              <div className="flex items-center gap-1">
                <GripHorizontal className="h-3.5 w-3.5 text-zinc-600" />
              </div>
            </div>
            <div className="min-h-[200px]">
              <MessageList />
              {streaming.isStreaming && (
                <div className="px-4 pb-4">
                  <StreamingIndicator />
                </div>
              )}
            </div>
          </div>

          {/* Dynamic tiles */}
          {hasSandbox && (
            <SandboxTile />
          )}

          {hasAgentSteps && (
            <AgentReasoningTile />
          )}

          {/* Custom tiles */}
          {customTiles.map((tile, i) => (
            <div
              key={`${tile.kind}-${i}`}
              className={`rounded-xl border border-zinc-800 bg-zinc-900/50 ${
                tile.minimized ? "" : ""
              }`}
            >
              <div className="flex items-center justify-between border-b border-zinc-800 px-4 py-2">
                <div className="flex items-center gap-2 text-xs font-medium text-zinc-500">
                  {tile.icon}
                  {tile.title}
                </div>
                <div className="flex items-center gap-1">
                  <button
                    onClick={() => toggleTileMinimize(i)}
                    className="rounded p-0.5 text-zinc-600 hover:bg-zinc-800 hover:text-zinc-400"
                  >
                    {tile.minimized ? (
                      <Maximize2 className="h-3.5 w-3.5" />
                    ) : (
                      <Minimize2 className="h-3.5 w-3.5" />
                    )}
                  </button>
                  <button
                    onClick={() => removeCustomTile(i)}
                    className="rounded p-0.5 text-zinc-600 hover:bg-zinc-800 hover:text-red-400"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
              {!tile.minimized && (
                <div className="p-4">
                  <TilePlaceholder kind={tile.kind} />
                </div>
              )}
            </div>
          ))}

          {/* Quick add tiles bar */}
          {messages.length > 0 && customTiles.length < 4 && (
            <div className="flex justify-center gap-1 py-2">
              {!customTiles.some((t) => t.kind === "code_sandbox") && (
                <button
                  onClick={() => addCustomTile("code_sandbox", "Code Sandbox", <Code2 className="h-4 w-4" />)}
                  className="flex items-center gap-1.5 rounded-lg border border-zinc-700/50 px-3 py-1.5 text-xs text-zinc-500 hover:border-zinc-600 hover:text-zinc-300 transition-colors"
                >
                  <Code2 className="h-3.5 w-3.5" />
                  Code Sandbox
                </button>
              )}
              {!customTiles.some((t) => t.kind === "browser_sandbox") && (
                <button
                  onClick={() => addCustomTile("browser_sandbox", "Browser", <Globe className="h-4 w-4" />)}
                  className="flex items-center gap-1.5 rounded-lg border border-zinc-700/50 px-3 py-1.5 text-xs text-zinc-500 hover:border-zinc-600 hover:text-zinc-300 transition-colors"
                >
                  <Globe className="h-3.5 w-3.5" />
                  Browser
                </button>
              )}
              {!customTiles.some((t) => t.kind === "agent_reasoning") && (
                <button
                  onClick={() => addCustomTile("agent_reasoning", "Agent Reasoning", <Brain className="h-4 w-4" />)}
                  className="flex items-center gap-1.5 rounded-lg border border-zinc-700/50 px-3 py-1.5 text-xs text-zinc-500 hover:border-zinc-600 hover:text-zinc-300 transition-colors"
                >
                  <Brain className="h-3.5 w-3.5" />
                  Reasoning
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function QuickAction({
  icon,
  label,
  onClick,
}: {
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="flex items-center gap-2 rounded-xl border border-zinc-700/50 bg-zinc-800/30 px-4 py-2.5 text-sm text-zinc-400 hover:border-zinc-600 hover:bg-zinc-800/50 hover:text-zinc-200 transition-all"
    >
      {icon}
      {label}
    </button>
  );
}

function TilePlaceholder({ kind }: { kind: string }) {
  switch (kind) {
    case "code_sandbox":
      return (
        <div className="rounded-lg bg-zinc-950 border border-zinc-800 p-4 font-mono text-sm">
          <div className="flex items-center gap-2 text-xs text-zinc-500 mb-2">
            <span className="rounded bg-zinc-800 px-1.5 py-0.5">main.py</span>
          </div>
          <pre className="text-green-400">
            <code>{`print("Hello from sandbox!")
result = 2 + 2
print(f"Result: {result}")`}</code>
          </pre>
          <div className="mt-2 text-zinc-500 text-xs">
            {'> '}Hello from sandbox!<br />
            {'> '}Result: 4
          </div>
        </div>
      );
    case "browser_sandbox":
      return (
        <div className="rounded-lg bg-zinc-950 border border-zinc-800 p-4 text-center text-sm text-zinc-500">
          <Globe className="mx-auto h-8 w-8 text-zinc-600 mb-2" />
          <p>Browser sandbox — navigate, click, capture</p>
          <p className="text-xs text-zinc-600 mt-1">
            Launch a browser container to interact with web pages
          </p>
        </div>
      );
    case "agent_reasoning":
      return (
        <div className="space-y-2 text-sm text-zinc-400">
          <div className="flex items-center gap-2 text-xs text-zinc-500">
            <Brain className="h-3.5 w-3.5" />
            Reasoning chain
          </div>
          <div className="rounded border border-zinc-800 bg-zinc-950 p-3 text-xs text-zinc-500">
            Step 1: Analyze the query to identify core requirements...
          </div>
          <div className="rounded border border-zinc-800 bg-zinc-950 p-3 text-xs text-zinc-500">
            Step 2: Search for relevant information and tool options...
          </div>
          <div className="rounded border border-zinc-800 bg-zinc-950 p-3 text-xs text-zinc-500">
            Step 3: Execute tools and evaluate results...
          </div>
        </div>
      );
    case "file_diff":
      return (
        <div className="rounded-lg bg-zinc-950 border border-zinc-800 p-4">
          <div className="text-xs text-zinc-500 mb-2">src/app/page.tsx</div>
          <div className="space-y-0.5 font-mono text-xs">
            <div className="text-zinc-500">  1  import &#123; db &#125; from &quot;@/db&quot;;</div>
            <div className="text-zinc-500">  2  import &#123; sql &#125; from &quot;drizzle-orm&quot;;</div>
            <div className="text-green-600 bg-green-600/5">+ 3  import &#123; threads &#125; from &quot;@/db/schema&quot;;</div>
            <div className="text-zinc-500">  4</div>
            <div className="text-zinc-500">  5  export const dynamic = &quot;force-dynamic&quot;;</div>
          </div>
        </div>
      );
    default:
      return (
        <div className="text-center text-sm text-zinc-500 py-4">
          Tile type: {kind}
        </div>
      );
  }
}
