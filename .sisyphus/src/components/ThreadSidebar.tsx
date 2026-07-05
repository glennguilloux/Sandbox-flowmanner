"use client";

import { useChatStore } from "@/lib/store";
import {
  Plus,
  Search,
  MessageSquare,
  Pin,
  Archive,
  Trash2,
  MoreHorizontal,
  Folder,
} from "lucide-react";
import { useState, useRef, useEffect } from "react";

export function ThreadSidebar() {
  const store = useChatStore();
  const {
    threads,
    activeThreadId,
    threadsLoading,
    fetchThreads,
    createThread,
    setActiveThread,
    deleteThread,
    updateThread,
  } = store;

  const [search, setSearch] = useState("");
  const [contextMenu, setContextMenu] = useState<{
    threadId: string;
    x: number;
    y: number;
  } | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setContextMenu(null);
      }
    };
    window.addEventListener("click", handler);
    return () => window.removeEventListener("click", handler);
  }, []);

  const filtered = threads.filter((t) =>
    t.title.toLowerCase().includes(search.toLowerCase()),
  );

  const pinned = filtered.filter((t) => t.isPinned);
  const unpinned = filtered.filter((t) => !t.isPinned);

  const handleNewThread = async () => {
    try {
      await createThread({ title: "New Chat" });
    } catch (e) {
      console.error("Failed to create thread:", e);
    }
  };

  const handleContextMenu = (
    e: React.MouseEvent,
    threadId: string,
  ) => {
    e.preventDefault();
    setContextMenu({ threadId, x: e.clientX, y: e.clientY });
  };

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2.5 border-b border-zinc-800">
        <span className="text-xs font-medium uppercase tracking-wider text-zinc-500">
          Threads
        </span>
        <button
          onClick={handleNewThread}
          className="rounded-md p-1 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-200 transition-colors"
          aria-label="New thread"
          title="New thread"
        >
          <Plus className="h-4 w-4" />
        </button>
      </div>

      {/* Search */}
      <div className="px-2 py-2">
        <div className="relative">
          <Search className="absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-zinc-500" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search threads..."
            className="w-full rounded-md border border-zinc-700 bg-zinc-800 py-1.5 pl-7 pr-2 text-xs text-zinc-200 placeholder-zinc-500 outline-none focus:border-zinc-600"
          />
        </div>
      </div>

      {/* Thread List */}
      <div className="flex-1 overflow-y-auto">
        {threadsLoading && (
          <div className="px-3 py-4 text-center text-xs text-zinc-500">
            Loading...
          </div>
        )}

        {!threadsLoading && filtered.length === 0 && (
          <div className="px-3 py-8 text-center">
            <MessageSquare className="mx-auto h-6 w-6 text-zinc-600" />
            <p className="mt-2 text-xs text-zinc-500">
              {search ? "No threads match your search" : "No threads yet"}
            </p>
            <button
              onClick={handleNewThread}
              className="mt-2 rounded-md bg-blue-600 px-3 py-1 text-xs text-white hover:bg-blue-500 transition-colors"
            >
              Start a new chat
            </button>
          </div>
        )}

        {/* Pinned threads */}
        {pinned.length > 0 && (
          <div>
            <div className="px-3 py-1 text-[10px] font-medium uppercase text-zinc-600">
              Pinned
            </div>
            {pinned.map((thread) => (
              <ThreadItem
                key={thread.id}
                thread={thread}
                isActive={thread.id === activeThreadId}
                onClick={() => setActiveThread(thread.id)}
                onContextMenu={(e) => handleContextMenu(e, thread.id)}
              />
            ))}
          </div>
        )}

        {/* Unpinned threads */}
        {unpinned.length > 0 && (
          <div>
            {pinned.length > 0 && (
              <div className="px-3 py-1 text-[10px] font-medium uppercase text-zinc-600">
                Recent
              </div>
            )}
            {unpinned.map((thread) => (
              <ThreadItem
                key={thread.id}
                thread={thread}
                isActive={thread.id === activeThreadId}
                onClick={() => setActiveThread(thread.id)}
                onContextMenu={(e) => handleContextMenu(e, thread.id)}
              />
            ))}
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="border-t border-zinc-800 px-3 py-2">
        <button className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-xs text-zinc-500 hover:bg-zinc-800 hover:text-zinc-300 transition-colors">
          <Folder className="h-3.5 w-3.5" />
          Workspaces
        </button>
      </div>

      {/* Context Menu */}
      {contextMenu && (
        <div
          ref={menuRef}
          className="fixed z-50 w-40 rounded-lg border border-zinc-700 bg-zinc-850 bg-zinc-900 p-1 shadow-xl"
          style={{ left: contextMenu.x, top: contextMenu.y }}
        >
          <button
            onClick={() => {
              updateThread(contextMenu.threadId, {
                isPinned: !threads.find((t) => t.id === contextMenu.threadId)
                  ?.isPinned,
              });
              setContextMenu(null);
            }}
            className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-xs text-zinc-300 hover:bg-zinc-800"
          >
            <Pin className="h-3 w-3" />
            {threads.find((t) => t.id === contextMenu.threadId)?.isPinned
              ? "Unpin"
              : "Pin"}
          </button>
          <button
            onClick={() => {
              updateThread(contextMenu.threadId, { isArchived: true });
              setContextMenu(null);
            }}
            className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-xs text-zinc-300 hover:bg-zinc-800"
          >
            <Archive className="h-3 w-3" />
            Archive
          </button>
          <button
            onClick={() => {
              deleteThread(contextMenu.threadId);
              setContextMenu(null);
            }}
            className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-xs text-red-400 hover:bg-red-600/20"
          >
            <Trash2 className="h-3 w-3" />
            Delete
          </button>
        </div>
      )}
    </div>
  );
}

function ThreadItem({
  thread,
  isActive,
  onClick,
  onContextMenu,
}: {
  thread: { id: string; title: string; isPinned: boolean | null; updatedAt: Date | null };
  isActive: boolean;
  onClick: () => void;
  onContextMenu: (e: React.MouseEvent) => void;
}) {
  const timeAgo = thread.updatedAt ? getTimeAgo(new Date(thread.updatedAt)) : "";

  return (
    <button
      onClick={onClick}
      onContextMenu={onContextMenu}
      className={`group flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs transition-colors ${
        isActive
          ? "bg-blue-600/10 text-blue-400"
          : "text-zinc-400 hover:bg-zinc-800/50 hover:text-zinc-200"
      }`}
    >
      <MessageSquare className="h-3.5 w-3.5 shrink-0" />
      <span className="flex-1 truncate">{thread.title || "Untitled"}</span>
      <span className="shrink-0 text-[10px] text-zinc-600 group-hover:hidden">
        {timeAgo}
      </span>
      {thread.isPinned && (
        <Pin className="h-3 w-3 shrink-0 text-zinc-600" />
      )}
    </button>
  );
}

function getTimeAgo(date: Date): string {
  const seconds = Math.floor((Date.now() - date.getTime()) / 1000);
  if (seconds < 60) return "now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h`;
  if (seconds < 604800) return `${Math.floor(seconds / 86400)}d`;
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}
