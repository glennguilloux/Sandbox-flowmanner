"use client";

import { useChatStore } from "@/lib/store";
import {
  Activity,
  Wrench,
  Brain,
  Shield,
  DollarSign,
  GitBranch,
  FileText,
  ChevronDown,
  ChevronRight,
} from "lucide-react";
import { useState } from "react";

export function AgentTracePanel() {
  const store = useChatStore();
  const { streaming, messages } = store;

  const [expandedSections, setExpandedSections] = useState<
    Record<string, boolean>
  >({
    activity: true,
    tools: true,
    reasoning: true,
    files: false,
    branches: false,
    cost: false,
  });

  const toggleSection = (section: string) => {
    setExpandedSections((prev) => ({
      ...prev,
      [section]: !prev[section],
    }));
  };

  // Collect tool calls from messages
  const allToolCalls = messages.flatMap((m) =>
    (m.steps || []).filter((s) => s.stepType === "tool"),
  );

  // Collect streaming activity
  const activeTools = Array.from(streaming.activeToolCalls.entries());
  const activeSteps = Array.from(streaming.activeSteps.entries());
  const toolResults = Array.from(streaming.toolResults.entries());

  const hasActivity =
    activeTools.length > 0 ||
    activeSteps.length > 0 ||
    streaming.isStreaming;

  return (
    <div className="flex h-full flex-col overflow-y-auto">
      {/* Activity feed */}
      <Section
        title="Activity"
        icon={<Activity className="h-3.5 w-3.5" />}
        isOpen={expandedSections.activity}
        onToggle={() => toggleSection("activity")}
        badge={
          hasActivity
            ? `${activeTools.length + activeSteps.length}`
            : undefined
        }
      >
        {hasActivity ? (
          <div className="space-y-1">
            {activeTools.map(([id, tc]) => (
              <div
                key={id}
                className="rounded-md bg-zinc-800/50 px-2 py-1.5 text-xs"
              >
                <div className="flex items-center gap-1.5">
                  <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-blue-400" />
                  <span className="text-zinc-400">
                    <strong className="text-zinc-300">{tc.toolName}</strong>
                  </span>
                </div>
                <div className="mt-0.5 text-[10px] text-zinc-600">
                  Tool call in progress
                </div>
              </div>
            ))}
            {toolResults.map(([id, tr]) => (
              <div
                key={id}
                className="rounded-md bg-zinc-800/50 px-2 py-1.5 text-xs"
              >
                <div className="flex items-center gap-1.5">
                  <span className="h-1.5 w-1.5 rounded-full bg-green-400" />
                  <span className="text-zinc-400">
                    <strong className="text-zinc-300">{tr.toolName}</strong>
                  </span>
                  <span className="ml-auto text-[10px] text-green-500">
                    {tr.status}
                  </span>
                </div>
              </div>
            ))}
            {streaming.isStreaming && activeTools.length === 0 && (
              <div className="rounded-md bg-zinc-800/50 px-2 py-1.5 text-xs text-zinc-500">
                <span className="animate-pulse">Streaming tokens...</span>
              </div>
            )}
          </div>
        ) : (
          <p className="text-xs text-zinc-600 px-2">
            No active events. Send a message to see agent activity here.
          </p>
        )}
      </Section>

      {/* Tool Calls */}
      <Section
        title="Tool Calls"
        icon={<Wrench className="h-3.5 w-3.5" />}
        isOpen={expandedSections.tools}
        onToggle={() => toggleSection("tools")}
        badge={allToolCalls.length > 0 ? `${allToolCalls.length}` : undefined}
      >
        {allToolCalls.length > 0 ? (
          <div className="space-y-1">
            {allToolCalls.slice(-20).map((step) => (
              <div
                key={step.id}
                className="rounded-md bg-zinc-800/50 px-2 py-1.5 text-xs"
              >
                <div className="flex items-center gap-1.5">
                  <span
                    className={`h-1.5 w-1.5 rounded-full ${
                      step.status === "completed"
                        ? "bg-green-400"
                        : step.status === "failed"
                          ? "bg-red-400"
                          : "bg-zinc-500"
                    }`}
                  />
                  <span className="text-zinc-400">{step.name}</span>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-xs text-zinc-600 px-2">No tool calls yet.</p>
        )}
      </Section>

      {/* Reasoning */}
      <Section
        title="Reasoning"
        icon={<Brain className="h-3.5 w-3.5" />}
        isOpen={expandedSections.reasoning}
        onToggle={() => toggleSection("reasoning")}
      >
        {streaming.reasoning ? (
          <div className="rounded-md bg-zinc-800/50 px-2 py-1.5 text-xs text-zinc-400">
            {streaming.reasoning}
          </div>
        ) : (
          <p className="text-xs text-zinc-600 px-2">
            Agent reasoning trace will appear here during multi-step tasks.
          </p>
        )}
      </Section>

      {/* Files Touched */}
      <Section
        title="Files Touched"
        icon={<FileText className="h-3.5 w-3.5" />}
        isOpen={expandedSections.files}
        onToggle={() => toggleSection("files")}
        badge={streaming.sandboxEvents.length > 0 ? `${streaming.sandboxEvents.length}` : undefined}
      >
        {streaming.sandboxEvents.length > 0 ? (
          <div className="space-y-1">
            {streaming.sandboxEvents.map((evt, i) => (
              <div
                key={i}
                className="rounded-md bg-zinc-800/50 px-2 py-1.5 text-xs text-zinc-400"
              >
                Sandbox: {evt.sandboxId} ({evt.status})
              </div>
            ))}
          </div>
        ) : (
          <p className="text-xs text-zinc-600 px-2">No files modified yet.</p>
        )}
      </Section>

      {/* Branches */}
      <Section
        title="Branches"
        icon={<GitBranch className="h-3.5 w-3.5" />}
        isOpen={expandedSections.branches}
        onToggle={() => toggleSection("branches")}
      >
        <p className="text-xs text-zinc-600 px-2">
          Conversation branches will appear when you fork messages.
        </p>
      </Section>

      {/* Cost */}
      <Section
        title="Cost"
        icon={<DollarSign className="h-3.5 w-3.5" />}
        isOpen={expandedSections.cost}
        onToggle={() => toggleSection("cost")}
      >
        <div className="space-y-1 px-2">
          <div className="flex justify-between text-xs">
            <span className="text-zinc-500">Tokens</span>
            <span className="text-zinc-400">
              {messages.reduce(
                (sum, m) => sum + (m.tokenCount || 0),
                0,
              ).toLocaleString()}
            </span>
          </div>
          <div className="flex justify-between text-xs">
            <span className="text-zinc-500">Cost</span>
            <span className="text-zinc-400">—</span>
          </div>
        </div>
      </Section>
    </div>
  );
}

function Section({
  title,
  icon,
  isOpen,
  onToggle,
  children,
  badge,
}: {
  title: string;
  icon: React.ReactNode;
  isOpen: boolean;
  onToggle: () => void;
  children: React.ReactNode;
  badge?: string;
}) {
  return (
    <div className="border-b border-zinc-800/50">
      <button
        onClick={onToggle}
        className="flex w-full items-center gap-2 px-3 py-2 text-left hover:bg-zinc-800/30 transition-colors"
      >
        {isOpen ? (
          <ChevronDown className="h-3 w-3 text-zinc-600" />
        ) : (
          <ChevronRight className="h-3 w-3 text-zinc-600" />
        )}
        <span className="text-zinc-500">{icon}</span>
        <span className="flex-1 text-xs font-medium text-zinc-400">
          {title}
        </span>
        {badge && (
          <span className="rounded-full bg-zinc-800 px-1.5 py-0.5 text-[10px] text-zinc-500">
            {badge}
          </span>
        )}
      </button>
      {isOpen && <div className="px-3 pb-2">{children}</div>}
    </div>
  );
}
