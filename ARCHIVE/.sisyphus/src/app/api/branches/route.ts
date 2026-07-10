import { NextRequest, NextResponse } from "next/server";
import { db } from "@/db";
import { branches, messages } from "@/db/schema";
import { eq } from "drizzle-orm";

export async function GET(req: NextRequest) {
  try {
    const { searchParams } = new URL(req.url);
    const threadId = searchParams.get("threadId");

    if (!threadId) {
      return NextResponse.json(
        { error: "threadId is required" },
        { status: 400 },
      );
    }

    const result = await db
      .select()
      .from(branches)
      .where(eq(branches.threadId, threadId));

    return NextResponse.json(result);
  } catch (e) {
    console.error("GET /api/branches error:", e);
    return NextResponse.json(
      { error: "Failed to fetch branches" },
      { status: 500 },
    );
  }
}

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();

    // Verify parent message exists
    const [parentMsg] = await db
      .select()
      .from(messages)
      .where(eq(messages.id, body.parentMessageId));

    if (!parentMsg) {
      return NextResponse.json(
        { error: "Parent message not found" },
        { status: 404 },
      );
    }

    const [branch] = await db
      .insert(branches)
      .values({
        threadId: body.threadId,
        parentMessageId: body.parentMessageId,
        title: body.title || `Branch at message`,
      })
      .returning();

    return NextResponse.json(branch, { status: 201 });
  } catch (e) {
    console.error("POST /api/branches error:", e);
    return NextResponse.json(
      { error: "Failed to create branch" },
      { status: 500 },
    );
  }
}
