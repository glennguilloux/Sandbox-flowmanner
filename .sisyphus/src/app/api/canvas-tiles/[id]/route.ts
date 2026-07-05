import { NextRequest, NextResponse } from "next/server";
import { db } from "@/db";
import { canvasTiles } from "@/db/schema";
import { eq } from "drizzle-orm";

export async function PATCH(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const { id } = await params;
    const body = await req.json();
    const [updated] = await db
      .update(canvasTiles)
      .set({ ...body, updatedAt: new Date() })
      .where(eq(canvasTiles.id, id))
      .returning();
    if (!updated) {
      return NextResponse.json({ error: "Tile not found" }, { status: 404 });
    }
    return NextResponse.json(updated);
  } catch (e) {
    console.error("PATCH /api/canvas-tiles/[id] error:", e);
    return NextResponse.json(
      { error: "Failed to update tile" },
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
    await db.delete(canvasTiles).where(eq(canvasTiles.id, id));
    return NextResponse.json({ success: true });
  } catch (e) {
    console.error("DELETE /api/canvas-tiles/[id] error:", e);
    return NextResponse.json(
      { error: "Failed to delete tile" },
      { status: 500 },
    );
  }
}
