import { NextRequest, NextResponse } from "next/server";
import { db } from "@/db";
import { sandboxes } from "@/db/schema";
import { eq, desc } from "drizzle-orm";

export async function GET(req: NextRequest) {
  try {
    const { searchParams } = new URL(req.url);
    const threadId = searchParams.get("threadId");
    const messageId = searchParams.get("messageId");

    let result;
    if (messageId) {
      result = await db
        .select()
        .from(sandboxes)
        .where(eq(sandboxes.messageId, messageId))
        .orderBy(desc(sandboxes.createdAt))
        .limit(1);
    } else if (threadId) {
      result = await db
        .select()
        .from(sandboxes)
        .where(eq(sandboxes.threadId, threadId))
        .orderBy(desc(sandboxes.createdAt));
    } else {
      result = await db
        .select()
        .from(sandboxes)
        .orderBy(desc(sandboxes.createdAt))
        .limit(20);
    }

    return NextResponse.json(result);
  } catch (e) {
    console.error("GET /api/sandboxes error:", e);
    return NextResponse.json(
      { error: "Failed to fetch sandboxes" },
      { status: 500 },
    );
  }
}

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const [sandbox] = await db
      .insert(sandboxes)
      .values({
        sandboxType: body.sandboxType || "code",
        language: body.language || "python",
        threadId: body.threadId,
        messageId: body.messageId,
        previewUrl: body.previewUrl,
        previewToken: body.previewToken,
        status: "creating",
        files: body.files,
        expiresAt: body.expiresAt,
      })
      .returning();
    return NextResponse.json(sandbox, { status: 201 });
  } catch (e) {
    console.error("POST /api/sandboxes error:", e);
    return NextResponse.json(
      { error: "Failed to create sandbox" },
      { status: 500 },
    );
  }
}
