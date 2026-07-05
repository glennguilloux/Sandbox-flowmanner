import { NextRequest, NextResponse } from "next/server";
import { db } from "@/db";
import { threads } from "@/db/schema";
import { eq, desc, and, SQL } from "drizzle-orm";

export async function GET(req: NextRequest) {
  try {
    const { searchParams } = new URL(req.url);
    const workspaceId = searchParams.get("workspaceId") || "default";
    const includeArchived = searchParams.get("includeArchived") === "true";

    const conditions: SQL[] = [eq(threads.workspaceId, workspaceId)];
    if (!includeArchived) {
      conditions.push(eq(threads.isArchived, false));
    }

    const result = await db
      .select()
      .from(threads)
      .where(and(...conditions))
      .orderBy(desc(threads.updatedAt));
    return NextResponse.json(result);
  } catch (e) {
    console.error("GET /api/threads error:", e);
    return NextResponse.json(
      { error: "Failed to fetch threads" },
      { status: 500 },
    );
  }
}

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const [thread] = await db
      .insert(threads)
      .values({
        title: body.title || "New Chat",
        workspaceId: body.workspaceId || "default",
        model: body.model || "gpt-4o",
        provider: body.provider || "openai",
        systemPrompt: body.systemPrompt,
        maxTokens: body.maxTokens,
        temperature: body.temperature,
        agentTeamId: body.agentTeamId,
      })
      .returning();
    return NextResponse.json(thread, { status: 201 });
  } catch (e) {
    console.error("POST /api/threads error:", e);
    return NextResponse.json(
      { error: "Failed to create thread" },
      { status: 500 },
    );
  }
}
