import { NextRequest, NextResponse } from "next/server";
import { db } from "@/db";
import { agentTeams } from "@/db/schema";

export async function GET() {
  try {
    const teams = await db.select().from(agentTeams);
    return NextResponse.json(teams);
  } catch (e) {
    console.error("GET /api/agent-teams error:", e);
    return NextResponse.json(
      { error: "Failed to fetch teams" },
      { status: 500 },
    );
  }
}

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const [team] = await db
      .insert(agentTeams)
      .values({
        name: body.name,
        description: body.description,
        members: body.members,
        protocol: body.protocol || "sequential",
        maxTurns: body.maxTurns || 10,
        escalationPolicy: body.escalationPolicy,
      })
      .returning();
    return NextResponse.json(team, { status: 201 });
  } catch (e) {
    console.error("POST /api/agent-teams error:", e);
    return NextResponse.json(
      { error: "Failed to create team" },
      { status: 500 },
    );
  }
}
