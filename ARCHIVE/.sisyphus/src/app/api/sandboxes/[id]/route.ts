import { NextRequest, NextResponse } from "next/server";
import { db } from "@/db";
import { sandboxes } from "@/db/schema";
import { eq } from "drizzle-orm";

export async function PATCH(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const { id } = await params;
    const body = await req.json();
    const [updated] = await db
      .update(sandboxes)
      .set(body)
      .where(eq(sandboxes.id, id))
      .returning();
    if (!updated) {
      return NextResponse.json(
        { error: "Sandbox not found" },
        { status: 404 },
      );
    }
    return NextResponse.json(updated);
  } catch (e) {
    console.error("PATCH /api/sandboxes/[id] error:", e);
    return NextResponse.json(
      { error: "Failed to update sandbox" },
      { status: 500 },
    );
  }
}
