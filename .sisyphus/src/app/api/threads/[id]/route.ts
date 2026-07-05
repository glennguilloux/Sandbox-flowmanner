import { NextRequest, NextResponse } from "next/server";
import { db } from "@/db";
import { threads } from "@/db/schema";
import { eq } from "drizzle-orm";

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const { id } = await params;
    const [thread] = await db
      .select()
      .from(threads)
      .where(eq(threads.id, id));
    if (!thread) {
      return NextResponse.json({ error: "Thread not found" }, { status: 404 });
    }
    return NextResponse.json(thread);
  } catch (e) {
    console.error("GET /api/threads/[id] error:", e);
    return NextResponse.json(
      { error: "Failed to fetch thread" },
      { status: 500 },
    );
  }
}

export async function PATCH(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const { id } = await params;
    const body = await req.json();
    const [updated] = await db
      .update(threads)
      .set({
        ...body,
        updatedAt: new Date(),
      })
      .where(eq(threads.id, id))
      .returning();
    if (!updated) {
      return NextResponse.json({ error: "Thread not found" }, { status: 404 });
    }
    return NextResponse.json(updated);
  } catch (e) {
    console.error("PATCH /api/threads/[id] error:", e);
    return NextResponse.json(
      { error: "Failed to update thread" },
      { status: 500 },
    );
  }
}

export async function DELETE(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const { id } = await params;
    await db.delete(threads).where(eq(threads.id, id));
    return NextResponse.json({ success: true });
  } catch (e) {
    console.error("DELETE /api/threads/[id] error:", e);
    return NextResponse.json(
      { error: "Failed to delete thread" },
      { status: 500 },
    );
  }
}
