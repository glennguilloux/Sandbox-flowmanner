"use client";

import { useChatStore } from "@/lib/store";
import { Code2, ExternalLink, RotateCw, Terminal, X } from "lucide-react";
import { useState } from "react";

export function SandboxTile() {
  const store = useChatStore();
  const { streaming, toggleSandboxPanel } = store;
  const [activeTab, setActiveTab] = useState<"output" | "preview">("output");

  const sandboxEvents = streaming.sandboxEvents;
  const latestSandbox = sandboxEvents[sandboxEvents.length - 1];

  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-zinc-800 px-4 py-2">
        <div className="flex items-center gap-2">
          <Code2 className="h-4 w-4 text-blue-400" />
          <span className="text-xs font-medium text-zinc-500">
            Code Sandbox
          </span>
          {latestSandbox && (
            <span
              className={`rounded-full px-1.5 py-0.5 text-[10px] ${
                latestSandbox.status === "running"
                  ? "bg-green-600/20 text-green-400"
                  : "bg-zinc-800 text-zinc-500"
              }`}
            >
              {latestSandbox.status}
            </span>
          )}
        </div>
        <div className="flex items-center gap-1">
          {/* Tab switcher */}
          <div className="flex rounded-md bg-zinc-800 p-0.5">
            <button
              onClick={() => setActiveTab("output")}
              className={`rounded px-2 py-0.5 text-[10px] font-medium transition-colors ${
                activeTab === "output"
                  ? "bg-zinc-700 text-zinc-200"
                  : "text-zinc-500 hover:text-zinc-300"
              }`}
            >
              <Terminal className="inline h-3 w-3 mr-1" />
              Output
            </button>
            <button
              onClick={() => setActiveTab("preview")}
              className={`rounded px-2 py-0.5 text-[10px] font-medium transition-colors ${
                activeTab === "preview"
                  ? "bg-zinc-700 text-zinc-200"
                  : "text-zinc-500 hover:text-zinc-300"
              }`}
            >
              <ExternalLink className="inline h-3 w-3 mr-1" />
              Preview
            </button>
          </div>
          <button className="rounded p-1 text-zinc-600 hover:bg-zinc-800 hover:text-zinc-400">
            <RotateCw className="h-3.5 w-3.5" />
          </button>
          <button
            onClick={toggleSandboxPanel}
            className="rounded p-1 text-zinc-600 hover:bg-zinc-800 hover:text-red-400"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="p-4">
        {activeTab === "output" ? (
          <div className="rounded-lg bg-zinc-950 border border-zinc-800 p-4">
            <div className="mb-2 text-[10px] font-medium uppercase text-zinc-600">
              Terminal Output
            </div>
            <pre className="font-mono text-xs text-green-400">
              <code>{`$ python main.py
Hello from sandbox!
Result: 4

Process exited with code 0
`}</code>
            </pre>
          </div>
        ) : (
          <div className="rounded-lg border border-zinc-800 bg-zinc-950">
            {/* Simulated iframe preview */}
            <div className="flex items-center gap-2 border-b border-zinc-800 px-3 py-1.5">
              <div className="flex gap-1.5">
                <span className="h-2.5 w-2.5 rounded-full bg-red-500/50" />
                <span className="h-2.5 w-2.5 rounded-full bg-yellow-500/50" />
                <span className="h-2.5 w-2.5 rounded-full bg-green-500/50" />
              </div>
              <span className="text-[10px] text-zinc-500">
                {latestSandbox?.previewUrl || "sandbox.preview.flowmanner.com"}
              </span>
            </div>
            <div className="flex items-center justify-center py-12">
              <div className="text-center">
                <div className="mb-2 text-4xl">🧪</div>
                <p className="text-sm text-zinc-400">
                  Sandbox preview active
                </p>
                <p className="text-xs text-zinc-600 mt-1">
                  {latestSandbox?.previewUrl || "Authenticated iframe would render here"}
                </p>
                <button className="mt-3 inline-flex items-center gap-1.5 rounded-md bg-blue-600 px-3 py-1.5 text-xs text-white hover:bg-blue-500 transition-colors">
                  <ExternalLink className="h-3 w-3" />
                  Open in new tab
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
