import { NextRequest, NextResponse } from "next/server";
import { db } from "@/db";
import { messages, agentSteps } from "@/db/schema";
import { eq, asc } from "drizzle-orm";

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const { id: threadId } = await params;
    const msgs = await db
      .select()
      .from(messages)
      .where(eq(messages.threadId, threadId))
      .orderBy(asc(messages.createdAt));

    // Fetch agent steps for all messages
    const messageIds = msgs.map((m) => m.id);
    let steps: (typeof agentSteps.$inferSelect)[] = [];
    if (messageIds.length > 0) {
      steps = await db
        .select()
        .from(agentSteps)
        .where(
          // Use a simple approach: fetch all steps and filter client-side
          // For large histories, add a proper join
          eq(agentSteps.messageId, messageIds[0]), // placeholder — we'll fix in a moment
        );
    }

    // Actually, better to fetch all steps for the thread's messages
    const allSteps = await db.select().from(agentSteps);

    const messagesWithSteps = msgs.map((msg) => ({
      ...msg,
      steps: allSteps.filter((s) => s.messageId === msg.id),
    }));

    return NextResponse.json(messagesWithSteps);
  } catch (e) {
    console.error("GET /api/threads/[id]/messages error:", e);
    return NextResponse.json(
      { error: "Failed to fetch messages" },
      { status: 500 },
    );
  }
}

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const { id: threadId } = await params;
    const body = await req.json();

    const [message] = await db
      .insert(messages)
      .values({
        threadId,
        role: body.role || "user",
        content: body.content || "",
        parentMessageId: body.parentMessageId,
        branchId: body.branchId,
        sandboxId: body.sandboxId,
      })
      .returning();

    // If the message has agent steps, insert them
    if (body.steps && Array.isArray(body.steps)) {
      const stepsToInsert = body.steps.map(
        (step: {
          stepType: string;
          status: string;
          name: string;
          displayName?: string;
          args?: unknown;
          result?: unknown;
          error?: string;
          agentName?: string;
          toolCallId?: string;
        }) => ({
          messageId: message.id,
          stepType: step.stepType,
          status: step.status || "pending",
          name: step.name,
          displayName: step.displayName,
          args: step.args,
          result: step.result,
          error: step.error,
          agentName: step.agentName,
          toolCallId: step.toolCallId,
        }),
      );
      await db.insert(agentSteps).values(stepsToInsert);
    }

    const steps = body.steps
      ? await db
          .select()
          .from(agentSteps)
          .where(eq(agentSteps.messageId, message.id))
      : [];

    return NextResponse.json({ ...message, steps }, { status: 201 });
  } catch (e) {
    console.error("POST /api/threads/[id]/messages error:", e);
    return NextResponse.json(
      { error: "Failed to create message" },
      { status: 500 },
    );
  }
}
