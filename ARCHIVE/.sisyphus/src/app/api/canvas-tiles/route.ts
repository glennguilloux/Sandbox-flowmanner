import { NextRequest, NextResponse } from "next/server";
import { db } from "@/db";
import { canvasTiles } from "@/db/schema";
import { eq, asc } from "drizzle-orm";

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

    const tiles = await db
      .select()
      .from(canvasTiles)
      .where(eq(canvasTiles.threadId, threadId))
      .orderBy(asc(canvasTiles.sortOrder));

    return NextResponse.json(tiles);
  } catch (e) {
    console.error("GET /api/canvas-tiles error:", e);
    return NextResponse.json(
      { error: "Failed to fetch canvas tiles" },
      { status: 500 },
    );
  }
}

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const [tile] = await db
      .insert(canvasTiles)
      .values({
        threadId: body.threadId,
        tileKind: body.tileKind || "chat",
        title: body.title,
        layout: body.layout,
        config: body.config,
        sortOrder: body.sortOrder || 0,
      })
      .returning();
    return NextResponse.json(tile, { status: 201 });
  } catch (e) {
    console.error("POST /api/canvas-tiles error:", e);
    return NextResponse.json(
      { error: "Failed to create canvas tile" },
      { status: 500 },
    );
  }
}
