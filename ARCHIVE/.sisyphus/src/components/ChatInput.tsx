"use client";

import { useState, useRef, useEffect, useCallback, KeyboardEvent } from "react";
import { useChatStore } from "@/lib/store";
import {
  Send,
  Square,
  Paperclip,
  Mic,
  Code2,
  Globe,
  Users,
  Sparkles,
} from "lucide-react";

const SLASH_COMMANDS = [
  { command: "/sandbox", description: "Open code sandbox", icon: <Code2 className="h-3.5 w-3.5" /> },
  { command: "/sandbox python", description: "Python sandbox", icon: <Code2 className="h-3.5 w-3.5" /> },
  { command: "/sandbox js", description: "JavaScript sandbox", icon: <Code2 className="h-3.5 w-3.5" /> },
  { command: "/spawn mission", description: "Create autonomous mission", icon: <Sparkles className="h-3.5 w-3.5" /> },
  { command: "/team engineering", description: "Activate engineering team", icon: <Users className="h-3.5 w-3.5" /> },
  { command: "/browser", description: "Open browser sandbox", icon: <Globe className="h-3.5 w-3.5" /> },
  { command: "/search", description: "Web search with RAG", icon: <Globe className="h-3.5 w-3.5" /> },
];

export function ChatInput() {
  const store = useChatStore();
  const { sendMessage, cancelStream, streaming } = store;

  const [input, setInput] = useState("");
  const [showCommands, setShowCommands] = useState(false);
  const [commandFilter, setCommandFilter] = useState("");
  const [selectedCommandIndex, setSelectedCommandIndex] = useState(0);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-resize textarea
  useEffect(() => {
    const ta = textareaRef.current;
    if (ta) {
      ta.style.height = "auto";
      ta.style.height = `${Math.min(ta.scrollHeight, 200)}px`;
    }
  }, [input]);

  // Focus textarea on mount
  useEffect(() => {
    textareaRef.current?.focus();
  }, []);

  // Handle slash commands
  const filteredCommands = commandFilter
    ? SLASH_COMMANDS.filter((c) =>
        c.command.toLowerCase().includes(commandFilter.toLowerCase()),
      )
    : SLASH_COMMANDS;

  const handleInputChange = (value: string) => {
    setInput(value);

    // Detect slash command
    if (value.startsWith("/") && !value.includes(" ")) {
      setShowCommands(true);
      setCommandFilter(value);
      setSelectedCommandIndex(0);
    } else if (value.startsWith("/")) {
      // Slash command with args — hide the picker
      setShowCommands(false);
    } else {
      setShowCommands(false);
    }
  };

  const applyCommand = (command: string) => {
    setInput(command + " ");
    setShowCommands(false);
    textareaRef.current?.focus();
  };

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      if (showCommands) {
        if (e.key === "ArrowDown") {
          e.preventDefault();
          setSelectedCommandIndex((prev) =>
            prev < filteredCommands.length - 1 ? prev + 1 : 0,
          );
        } else if (e.key === "ArrowUp") {
          e.preventDefault();
          setSelectedCommandIndex((prev) =>
            prev > 0 ? prev - 1 : filteredCommands.length - 1,
          );
        } else if (e.key === "Enter" || e.key === "Tab") {
          e.preventDefault();
          if (filteredCommands[selectedCommandIndex]) {
            applyCommand(filteredCommands[selectedCommandIndex].command);
          }
        } else if (e.key === "Escape") {
          setShowCommands(false);
        }
        return;
      }

      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    },
    [showCommands, selectedCommandIndex, filteredCommands, input],
  );

  const handleSend = () => {
    const trimmed = input.trim();
    if (!trimmed || streaming.isStreaming) return;
    setInput("");
    sendMessage(trimmed);
  };

  return (
    <div className="border-t border-zinc-800 bg-zinc-900/80 backdrop-blur-sm">
      <div className="mx-auto max-w-4xl p-3">
        {/* Slash command picker */}
        {showCommands && filteredCommands.length > 0 && (
          <div className="mb-2 rounded-lg border border-zinc-700 bg-zinc-850 bg-zinc-900 p-1 shadow-xl">
            {filteredCommands.map((cmd, i) => (
              <button
                key={cmd.command}
                onClick={() => applyCommand(cmd.command)}
                className={`flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs ${
                  i === selectedCommandIndex
                    ? "bg-blue-600/20 text-blue-400"
                    : "text-zinc-400 hover:bg-zinc-800"
                }`}
              >
                <span className="text-zinc-500">{cmd.icon}</span>
                <span className="font-medium">{cmd.command}</span>
                <span className="ml-auto text-zinc-600">
                  {cmd.description}
                </span>
              </button>
            ))}
          </div>
        )}

        {/* Input area */}
        <div className="flex items-end gap-2 rounded-xl border border-zinc-700 bg-zinc-800 px-3 py-2 focus-within:border-zinc-600 transition-colors">
          {/* Attachment button */}
          <button className="rounded-md p-1.5 text-zinc-500 hover:bg-zinc-700 hover:text-zinc-300 transition-colors shrink-0">
            <Paperclip className="h-4 w-4" />
          </button>

          {/* Textarea */}
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => handleInputChange(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={
              streaming.isStreaming
                ? "Waiting for response..."
                : "Send a message... (⌘↵ to send, / for commands)"
            }
            rows={1}
            disabled={streaming.isStreaming}
            className="flex-1 resize-none bg-transparent py-1 text-sm text-zinc-200 placeholder-zinc-500 outline-none disabled:opacity-50"
            id="chat-input"
            name="chat-input"
          />

          {/* Mic button */}
          <button className="rounded-md p-1.5 text-zinc-500 hover:bg-zinc-700 hover:text-zinc-300 transition-colors shrink-0">
            <Mic className="h-4 w-4" />
          </button>

          {/* Send / Stop button */}
          {streaming.isStreaming ? (
            <button
              onClick={cancelStream}
              className="flex items-center gap-1.5 rounded-lg bg-red-600/20 px-3 py-1.5 text-xs font-medium text-red-400 hover:bg-red-600/30 transition-colors shrink-0"
            >
              <Square className="h-3.5 w-3.5" />
              Stop
            </button>
          ) : (
            <button
              onClick={handleSend}
              disabled={!input.trim()}
              className="flex items-center gap-1.5 rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed transition-colors shrink-0"
              aria-label="Send message"
            >
              <Send className="h-3.5 w-3.5" />
              Send
            </button>
          )}
        </div>

        {/* Hint bar */}
        <div className="mt-1.5 flex items-center justify-center gap-3 text-[10px] text-zinc-600">
          <span>
            <kbd className="rounded border border-zinc-700 px-1 py-0.5 text-[9px]">⌘↵</kbd>{" "}
            Send
          </span>
          <span>
            <kbd className="rounded border border-zinc-700 px-1 py-0.5 text-[9px]">Shift↵</kbd>{" "}
            New line
          </span>
          <span>
            <kbd className="rounded border border-zinc-700 px-1 py-0.5 text-[9px]">/</kbd>{" "}
            Commands
          </span>
          <span className="hidden sm:inline">
            <kbd className="rounded border border-zinc-700 px-1 py-0.5 text-[9px]">⌘B</kbd>{" "}
            Sidebar
          </span>
          <span className="hidden sm:inline">
            <kbd className="rounded border border-zinc-700 px-1 py-0.5 text-[9px]">⌘J</kbd>{" "}
            Trace
          </span>
        </div>
      </div>
    </div>
  );
}
