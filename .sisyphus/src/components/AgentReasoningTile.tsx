"use client";

import { useChatStore } from "@/lib/store";
import { Brain, ChevronRight, Check, Loader2, X } from "lucide-react";

export function AgentReasoningTile() {
  const store = useChatStore();
  const { streaming } = store;

  const steps = Array.from(streaming.activeSteps.values());

  if (steps.length === 0) return null;

  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 overflow-hidden">
      <div className="flex items-center gap-2 border-b border-zinc-800 px-4 py-2">
        <Brain className="h-4 w-4 text-purple-400" />
        <span className="text-xs font-medium text-zinc-500">
          Agent Reasoning
        </span>
        <span className="ml-auto rounded-full bg-purple-600/20 px-1.5 py-0.5 text-[10px] text-purple-400">
          {steps.length} active
        </span>
      </div>
      <div className="p-4 space-y-2">
        {steps.map((step) => (
          <div
            key={step.stepId}
            className="flex items-start gap-3 rounded-lg border border-zinc-800 bg-zinc-950 p-3"
          >
            {step.status === "completed" ? (
              <Check className="mt-0.5 h-4 w-4 shrink-0 text-green-500" />
            ) : step.status === "failed" ? (
              <X className="mt-0.5 h-4 w-4 shrink-0 text-red-500" />
            ) : (
              <Loader2 className="mt-0.5 h-4 w-4 shrink-0 animate-spin text-yellow-500" />
            )}
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-xs font-medium text-zinc-300">
                  {step.displayName || step.name}
                </span>
                <span className="text-[10px] text-zinc-600">
                  {step.agentName}
                </span>
              </div>
              <div className="mt-0.5 text-xs text-zinc-500">
                {step.stepType === "tool" && "Invoking tool..."}
                {step.stepType === "reasoning" && "Analyzing and planning..."}
                {step.stepType === "handoff" && "Handing off to sub-agent..."}
                {step.stepType === "sandbox" && "Running in sandbox..."}
                {step.stepType === "permission" && "Waiting for approval..."}
              </div>
            </div>
          </div>
        ))}

        {/* Reasoning chain visualization */}
        <div className="mt-3 space-y-1.5">
          <div className="text-[10px] font-medium uppercase text-zinc-600">
            Reasoning Chain
          </div>
          <div className="flex items-center gap-1 text-xs text-zinc-500">
            <span className="rounded bg-zinc-800 px-2 py-1 text-zinc-400">
              Analyze
            </span>
            <ChevronRight className="h-3 w-3 text-zinc-600" />
            <span className="rounded bg-zinc-800 px-2 py-1 text-zinc-400">
              Plan
            </span>
            <ChevronRight className="h-3 w-3 text-zinc-600" />
            <span className="rounded bg-purple-600/20 px-2 py-1 text-purple-400">
              Execute
            </span>
            <ChevronRight className="h-3 w-3 text-zinc-600" />
            <span className="rounded bg-zinc-800 px-2 py-1 text-zinc-600">
              Verify
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
