"use client";

import { useChatStore } from "@/lib/store";
import type { ChatMessage } from "@/lib/types";
import { safeStringify } from "@/lib/utils";
import {
  User,
  Bot,
  Wrench,
  Brain,
  ExternalLink,
  Check,
  X,
  ChevronDown,
  ChevronRight,
  RefreshCw,
  Copy,
  ThumbsUp,
  ThumbsDown,
  GitBranch,
} from "lucide-react";
import { useState } from "react";

export function MessageList() {
  const store = useChatStore();
  const { messages } = store;

  if (messages.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-center">
        <Bot className="h-10 w-10 text-zinc-700" />
        <p className="mt-3 text-sm text-zinc-500">
          Send a message to start. Use{" "}
          <kbd className="rounded border border-zinc-700 px-1.5 py-0.5 text-xs text-zinc-400">
            /sandbox
          </kbd>{" "}
          for code execution, or{" "}
          <kbd className="rounded border border-zinc-700 px-1.5 py-0.5 text-xs text-zinc-400">
            /spawn mission
          </kbd>{" "}
          for autonomous agents.
        </p>
      </div>
    );
  }

  return (
    <div className="divide-y divide-zinc-800/50">
      {messages.map((msg) => (
        <MessageRow key={msg.id} message={msg} />
      ))}
    </div>
  );
}

function MessageRow({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  const isAssistant = message.role === "assistant";
  const hasSteps = message.steps && message.steps.length > 0;

  return (
    <div
      className={`group px-4 py-4 ${
        isAssistant ? "bg-zinc-900/30" : ""
      }`}
    >
      <div className="flex gap-3">
        {/* Avatar */}
        <div
          className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full ${
            isUser
              ? "bg-blue-600/20 text-blue-400"
              : "bg-purple-600/20 text-purple-400"
          }`}
        >
          {isUser ? (
            <User className="h-4 w-4" />
          ) : message.role === "system" ? (
            <Wrench className="h-4 w-4" />
          ) : (
            <Bot className="h-4 w-4" />
          )}
        </div>

        {/* Content */}
        <div className="min-w-0 flex-1">
          {/* Role label */}
          <div className="mb-1 flex items-center gap-2">
            <span className="text-xs font-medium text-zinc-500">
              {isUser ? "You" : isAssistant ? "Assistant" : message.role}
            </span>
            {message.isRegenerated && (
              <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-[10px] text-zinc-500">
                Regenerated
              </span>
            )}
            {message.branchId && (
              <span className="flex items-center gap-1 rounded bg-zinc-800 px-1.5 py-0.5 text-[10px] text-zinc-500">
                <GitBranch className="h-2.5 w-2.5" />
                Branch
              </span>
            )}
          </div>

          {/* Message content with markdown-like rendering */}
          <div className="prose prose-invert prose-sm max-w-none text-sm leading-relaxed text-zinc-300">
            <RenderedContent content={message.content} />
          </div>

          {/* Reasoning (for assistant messages) */}
          {message.reasoning && (
            <ReasoningBlock reasoning={message.reasoning} />
          )}

          {/* Agent steps */}
          {hasSteps && (
            <div className="mt-3 space-y-1.5">
              {message.steps!.map((step) => (
                <AgentStepCard key={step.id} step={step} />
              ))}
            </div>
          )}

          {/* Citations */}
          {message.citations && message.citations.length > 0 && (
            <div className="mt-3 space-y-1">
              <div className="text-xs font-medium text-zinc-500">
                Sources
              </div>
              {message.citations.map((c, i) => (
                <div
                  key={i}
                  className="flex items-center gap-2 rounded border border-zinc-800 bg-zinc-900 px-2.5 py-1.5 text-xs"
                >
                  <ExternalLink className="h-3 w-3 shrink-0 text-zinc-500" />
                  <span className="text-zinc-400">{c.source}</span>
                  <span className="text-zinc-600">
                    {(c.score * 100).toFixed(0)}%
                  </span>
                </div>
              ))}
            </div>
          )}

          {/* Message actions (hover) */}
          {isAssistant && (
            <div className="mt-2 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
              <button
                className="rounded p-1 text-zinc-600 hover:bg-zinc-800 hover:text-zinc-400"
                title="Copy"
              >
                <Copy className="h-3.5 w-3.5" />
              </button>
              <button
                className="rounded p-1 text-zinc-600 hover:bg-zinc-800 hover:text-green-400"
                title="Good response"
              >
                <ThumbsUp className="h-3.5 w-3.5" />
              </button>
              <button
                className="rounded p-1 text-zinc-600 hover:bg-zinc-800 hover:text-red-400"
                title="Bad response"
              >
                <ThumbsDown className="h-3.5 w-3.5" />
              </button>
              <button
                className="rounded p-1 text-zinc-600 hover:bg-zinc-800 hover:text-zinc-400"
                title="Regenerate"
              >
                <RefreshCw className="h-3.5 w-3.5" />
              </button>
              <button
                className="rounded p-1 text-zinc-600 hover:bg-zinc-800 hover:text-zinc-400"
                title="Branch from here"
              >
                <GitBranch className="h-3.5 w-3.5" />
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function RenderedContent({ content }: { content: string }) {
  // Simple markdown rendering: code blocks, inline code, bold, links
  const parts = content.split(/(```[\s\S]*?```|`[^`]+`|\*\*[^*]+\*\*)/g);

  return (
    <>
      {parts.map((part, i) => {
        if (part.startsWith("```") && part.endsWith("```")) {
          const lines = part.slice(3, -3).split("\n");
          const lang = lines[0]?.trim() || "";
          const code = lang ? lines.slice(1).join("\n") : lines.join("\n");
          return (
            <div
              key={i}
              className="my-2 overflow-x-auto rounded-lg border border-zinc-800 bg-zinc-950"
            >
              {lang && (
                <div className="flex items-center justify-between border-b border-zinc-800 px-3 py-1.5">
                  <span className="text-xs text-zinc-500">{lang}</span>
                  <button
                    className="rounded p-0.5 text-zinc-600 hover:text-zinc-400"
                    onClick={() => navigator.clipboard.writeText(code.trim())}
                  >
                    <Copy className="h-3 w-3" />
                  </button>
                </div>
              )}
              <pre className="p-3 text-xs">
                <code>{code.trim()}</code>
              </pre>
            </div>
          );
        }
        if (part.startsWith("`") && part.endsWith("`")) {
          return (
            <code
              key={i}
              className="rounded bg-zinc-800 px-1 py-0.5 text-xs text-zinc-300"
            >
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

function ReasoningBlock({ reasoning }: { reasoning: string }) {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <div className="mt-2">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-1.5 text-xs text-zinc-500 hover:text-zinc-400 transition-colors"
      >
        <Brain className="h-3.5 w-3.5" />
        Reasoning
        {isOpen ? (
          <ChevronDown className="h-3 w-3" />
        ) : (
          <ChevronRight className="h-3 w-3" />
        )}
      </button>
      {isOpen && (
        <div className="mt-1.5 rounded border border-zinc-800 bg-zinc-950 p-3 text-xs text-zinc-400 leading-relaxed">
          {reasoning}
        </div>
      )}
    </div>
  );
}

function AgentStepCard({
  step,
}: {
  step: {
    id: string;
    stepType: string;
    status: string;
    name: string;
    displayName?: string | null;
    result?: unknown;
    error?: string | null;
    agentName?: string | null;
  };
}) {
  const [isOpen, setIsOpen] = useState(false);
  const isCompleted = step.status === "completed";
  const isFailed = step.status === "failed";
  const isRunning = step.status === "running";

  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-950/50 overflow-hidden">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex w-full items-center gap-2 px-3 py-2 text-xs hover:bg-zinc-800/30 transition-colors"
      >
        {/* Status icon */}
        {isCompleted ? (
          <Check className="h-3.5 w-3.5 text-green-500" />
        ) : isFailed ? (
          <X className="h-3.5 w-3.5 text-red-500" />
        ) : isRunning ? (
          <span className="flex h-3.5 w-3.5 items-center justify-center">
            <span className="h-2 w-2 animate-pulse rounded-full bg-yellow-500" />
          </span>
        ) : (
          <span className="flex h-3.5 w-3.5 items-center justify-center">
            <span className="h-2 w-2 rounded-full bg-zinc-600" />
          </span>
        )}

        {/* Step type and name */}
        <span className="font-medium text-zinc-400">
          {step.stepType === "tool" && "Tool: "}
          {step.stepType === "reasoning" && "Reasoning: "}
          {step.stepType === "handoff" && "Handoff: "}
          {step.stepType === "sandbox" && "Sandbox: "}
          {step.displayName || step.name}
        </span>

        {/* Agent name */}
        {step.agentName && (
          <span className="ml-auto text-zinc-600">{step.agentName}</span>
        )}

        <ChevronDown
          className={`h-3 w-3 shrink-0 text-zinc-600 transition-transform ${
            isOpen ? "rotate-180" : ""
          }`}
        />
      </button>

      {isOpen && step.result != null && (
        <div className="border-t border-zinc-800 px-3 py-2">
          <pre className="max-h-40 overflow-auto text-xs text-zinc-400">
            {typeof step.result === "string"
              ? step.result
              : safeStringify(step.result)}
          </pre>
        </div>
      )}

      {isOpen && step.error && (
        <div className="border-t border-red-800/30 px-3 py-2 text-xs text-red-400">
          {step.error}
        </div>
      )}
    </div>
  );
}
