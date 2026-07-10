import { NextRequest, NextResponse } from "next/server";
import { db } from "@/db";
import { toolDefinitions, workspaceToolPermissions } from "@/db/schema";
import { eq } from "drizzle-orm";

export async function GET(req: NextRequest) {
  try {
    const { searchParams } = new URL(req.url);
    const workspaceId = searchParams.get("workspaceId") || "default";

    // Fetch all enabled tools
    const tools = await db
      .select()
      .from(toolDefinitions)
      .where(eq(toolDefinitions.isEnabled, true));

    // Fetch workspace permissions
    const permissions = await db
      .select()
      .from(workspaceToolPermissions)
      .where(eq(workspaceToolPermissions.workspaceId, workspaceId));

    const allowedToolIds = new Set(
      permissions.filter((p) => p.isAllowed).map((p) => p.toolId),
    );

    const toolsWithPermissions = tools.map((tool) => ({
      ...tool,
      isAllowed: allowedToolIds.has(tool.id),
      requiresApproval: tool.requiresApproval,
    }));

    return NextResponse.json(toolsWithPermissions);
  } catch (e) {
    console.error("GET /api/tools error:", e);
    return NextResponse.json(
      { error: "Failed to fetch tools" },
      { status: 500 },
    );
  }
}

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const [tool] = await db
      .insert(toolDefinitions)
      .values({
        name: body.name,
        displayName: body.displayName || body.name,
        description: body.description,
        category: body.category || "utility",
        inputSchema: body.inputSchema,
        requiredScopes: body.requiredScopes,
        rateLimitPerMin: body.rateLimitPerMin,
        requiresSandbox: body.requiresSandbox || false,
        requiresApproval: body.requiresApproval || false,
      })
      .returning();
    return NextResponse.json(tool, { status: 201 });
  } catch (e) {
    console.error("POST /api/tools error:", e);
    return NextResponse.json(
      { error: "Failed to create tool" },
      { status: 500 },
    );
  }
}
