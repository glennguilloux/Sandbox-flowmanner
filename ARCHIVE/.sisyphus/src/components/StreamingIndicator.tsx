"use client";

import { useChatStore } from "@/lib/store";
import { Loader2 } from "lucide-react";

export function StreamingIndicator() {
  const store = useChatStore();
  const { streaming } = store;

  if (!streaming.isStreaming) return null;

  const hasContent = streaming.content.length > 0;
  const activeTools = Array.from(streaming.activeToolCalls.entries());
  const activeSteps = Array.from(streaming.activeSteps.values());
  const citations = streaming.citations;

  return (
    <div className="space-y-2">
      {/* Streaming text */}
      {streaming.content && (
        <div className="text-sm leading-relaxed text-zinc-300">
          <RenderedStreamingContent content={streaming.content} />
          <span className="inline-block w-1.5 h-4 ml-0.5 bg-zinc-400 animate-pulse align-middle" />
        </div>
      )}

      {/* Active tool calls */}
      {activeTools.map(([id, tc]) => (
        <div
          key={id}
          className="flex items-center gap-2 rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2 text-xs"
        >
          <Loader2 className="h-3.5 w-3.5 animate-spin text-blue-400" />
          <span className="text-zinc-400">
            Calling <span className="font-medium text-zinc-300">{tc.toolName}</span>
            ...
          </span>
        </div>
      ))}

      {/* Active agent steps */}
      {activeSteps.map((step) => (
        <div
          key={step.stepId}
          className="flex items-center gap-2 rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2 text-xs"
        >
          <Loader2 className="h-3.5 w-3.5 animate-spin text-purple-400" />
          <span className="text-zinc-400">
            {step.displayName || step.name}
          </span>
        </div>
      ))}

      {/* Citations streaming in */}
      {citations.length > 0 && (
        <div className="text-xs text-zinc-500">
          Found {citations.length} source{citations.length > 1 ? "s" : ""}
        </div>
      )}

      {/* Error */}
      {streaming.error && (
        <div className="rounded-lg border border-red-800/30 bg-red-600/10 px-3 py-2 text-xs text-red-400">
          {streaming.error}
        </div>
      )}

      {/* Waiting for first token */}
      {!hasContent && activeTools.length === 0 && activeSteps.length === 0 && (
        <div className="flex items-center gap-2 text-xs text-zinc-500 py-1">
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
          Thinking...
        </div>
      )}
    </div>
  );
}

function RenderedStreamingContent({ content }: { content: string }) {
  // Simple inline markdown for streaming text — just handle code and bold
  const parts = content.split(/(```[\s\S]*?(?:```|$)|`[^`]+`|\*\*[^*]+\*\*)/g);

  return (
    <>
      {parts.map((part, i) => {
        if (part.startsWith("```")) {
          const code = part.slice(3).replace(/```$/, "");
          return (
            <code key={i} className="block rounded bg-zinc-800 px-2 py-1 my-1 text-xs">
              {code || "..."}
            </code>
          );
        }
        if (part.startsWith("`") && part.endsWith("`")) {
          return (
            <code key={i} className="rounded bg-zinc-800 px-1 py-0.5 text-xs">
              {part.slice(1, -1)}
            </code>
          );
        }
        if (part.startsWith("**") && part.endsWith("**")) {
          return (
            <strong key={i} className="font-semibold text-zinc-200">
              {part.slice(2, -2)}
            </strong>
          );
        }
        return <span key={i}>{part}</span>;
      })}
    </>
  );
}
