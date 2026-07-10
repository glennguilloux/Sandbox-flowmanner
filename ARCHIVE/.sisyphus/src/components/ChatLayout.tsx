"use client";

import { useEffect, useCallback, useRef, useState } from "react";
import { useChatStore } from "@/lib/store";
import { ThreadSidebar } from "./ThreadSidebar";
import { Canvas } from "./Canvas";
import { AgentTracePanel } from "./AgentTracePanel";
import { TopBar } from "./TopBar";
import { ChatInput } from "./ChatInput";
import {
  PanelLeftOpen,
  PanelLeftClose,
  PanelRightOpen,
  PanelRightClose,
  Maximize2,
  Minimize2,
} from "lucide-react";

export function ChatLayout() {
  const store = useChatStore();
  const {
    activeThreadId,
    isZenMode,
    isMobileSidebarOpen,
    isRightSidebarOpen,
    toggleZenMode,
    toggleMobileSidebar,
    toggleRightSidebar,
    fetchThreads,
    fetchMessages,
    fetchTools,
    fetchTiles,
  } = store;

  const [isMobile, setIsMobile] = useState(false);
  const mobileCheckRef = useRef<ReturnType<typeof setTimeout>>(null);

  // Detect mobile
  useEffect(() => {
    const check = () => {
      const mobile = window.innerWidth < 1024;
      setIsMobile(mobile);
    };
    check();
    const handler = () => {
      if (mobileCheckRef.current) clearTimeout(mobileCheckRef.current);
      mobileCheckRef.current = setTimeout(check, 100);
    };
    window.addEventListener("resize", handler);
    return () => window.removeEventListener("resize", handler);
  }, []);

  // Initial data fetch
  useEffect(() => {
    fetchThreads();
    fetchTools();
  }, [fetchThreads, fetchTools]);

  // Fetch messages and tiles when thread changes
  useEffect(() => {
    if (activeThreadId) {
      fetchMessages(activeThreadId);
      fetchTiles(activeThreadId);
    }
  }, [activeThreadId, fetchMessages, fetchTiles]);

  // Keyboard shortcuts
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey;
      if (mod && e.key === "b") {
        e.preventDefault();
        toggleMobileSidebar();
      }
      if (mod && e.key === "j") {
        e.preventDefault();
        toggleRightSidebar();
      }
      if (mod && e.key === "z" && e.shiftKey) {
        e.preventDefault();
        toggleZenMode();
      }
    },
    [toggleMobileSidebar, toggleRightSidebar, toggleZenMode],
  );

  useEffect(() => {
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handleKeyDown]);

  const showLeftSidebar = !isZenMode && (isMobileSidebarOpen || !isMobile);
  const showRightSidebar = !isZenMode && isRightSidebarOpen && !isMobile;

  return (
    <div className="flex h-screen flex-col bg-zinc-950 text-zinc-100">
      {/* Top Bar */}
      <TopBar />

      <div className="flex flex-1 overflow-hidden">
        {/* Left Sidebar — Threads */}
        {showLeftSidebar && (
          <aside
            className={`${
              isMobile
                ? "absolute inset-y-0 left-0 z-40 w-72 shadow-2xl"
                : "relative w-64 shrink-0"
            } flex flex-col border-r border-zinc-800 bg-zinc-900`}
          >
            {isMobile && (
              <button
                onClick={toggleMobileSidebar}
                className="absolute right-2 top-2 rounded-md p-1 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200"
                aria-label="Close sidebar"
              >
                <PanelLeftClose className="h-4 w-4" />
              </button>
            )}
            <ThreadSidebar />
          </aside>
        )}

        {/* Mobile overlay */}
        {isMobile && isMobileSidebarOpen && (
          <div
            className="fixed inset-0 z-30 bg-black/50"
            onClick={toggleMobileSidebar}
          />
        )}

        {/* Main Canvas */}
        <main className="flex flex-1 flex-col overflow-hidden">
          {/* Toggle buttons when sidebars hidden */}
          <div className="flex items-center gap-1 px-2 py-1">
            {!showLeftSidebar && !isMobile && (
              <button
                onClick={toggleMobileSidebar}
                className="rounded-md p-1.5 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-300"
                aria-label="Show threads"
                title="Show threads sidebar (⌘B)"
              >
                <PanelLeftOpen className="h-4 w-4" />
              </button>
            )}
            <div className="flex-1" />
            <button
              onClick={toggleZenMode}
              className="rounded-md p-1.5 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-300"
              aria-label={isZenMode ? "Exit zen mode" : "Zen mode"}
              title={isZenMode ? "Exit zen mode (⌘⇧Z)" : "Zen mode (⌘⇧Z)"}
            >
              {isZenMode ? (
                <Minimize2 className="h-4 w-4" />
              ) : (
                <Maximize2 className="h-4 w-4" />
              )}
            </button>
            {!showRightSidebar && !isMobile && (
              <button
                onClick={toggleRightSidebar}
                className="rounded-md p-1.5 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-300"
                aria-label="Show agent trace"
                title="Show agent trace (⌘J)"
              >
                <PanelRightOpen className="h-4 w-4" />
              </button>
            )}
          </div>

          <Canvas />
          <ChatInput />
        </main>

        {/* Right Sidebar — Agent Trace */}
        {showRightSidebar && (
          <aside className="w-72 shrink-0 border-l border-zinc-800 bg-zinc-900">
            <div className="flex items-center justify-between border-b border-zinc-800 px-3 py-2">
              <span className="text-xs font-medium uppercase tracking-wider text-zinc-500">
                Agent Trace
              </span>
              <button
                onClick={toggleRightSidebar}
                className="rounded-md p-1 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-300"
                aria-label="Close agent trace"
              >
                <PanelRightClose className="h-4 w-4" />
              </button>
            </div>
            <AgentTracePanel />
          </aside>
        )}
      </div>
    </div>
  );
}
