import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";

export const metadata: Metadata = {
  title: "FlowManner — Hybrid Chat + Tools + Agents + Sandbox",
  description: "A canvas-first hybrid platform where chat, tools, agents, and sandboxes are equal first-class surfaces.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-slate-100 text-slate-900 antialiased">{children}</body>
    </html>
  );
}
