import {
  pgTable,
  text,
  timestamp,
  uuid,
  jsonb,
  integer,
  boolean,
  pgEnum,
  index,
} from "drizzle-orm/pg-core";

// ── Enums ──────────────────────────────────────────────────────────────────

export const messageRoleEnum = pgEnum("message_role", [
  "user",
  "assistant",
  "system",
  "tool",
  "agent",
]);

export const agentStepTypeEnum = pgEnum("agent_step_type", [
  "tool",
  "reasoning",
  "handoff",
  "sandbox",
  "permission",
]);

export const agentStepStatusEnum = pgEnum("agent_step_status", [
  "pending",
  "running",
  "completed",
  "failed",
  "awaiting_approval",
  "cancelled",
]);

export const tileKindEnum = pgEnum("tile_kind", [
  "chat",
  "code_sandbox",
  "browser_sandbox",
  "agent_reasoning",
  "file_diff",
  "image_gen",
  "mission_status",
]);

export const providerEnum = pgEnum("provider_enum", [
  "openai",
  "anthropic",
  "google",
  "groq",
  "together",
  "local",
]);

// ── Threads ────────────────────────────────────────────────────────────────

export const threads = pgTable(
  "threads",
  {
    id: uuid("id").defaultRandom().primaryKey(),
    title: text("title").notNull().default("New Chat"),
    workspaceId: text("workspace_id").default("default"),
    model: text("model").notNull().default("gpt-4o"),
    provider: providerEnum("provider").notNull().default("openai"),
    systemPrompt: text("system_prompt"),
    maxTokens: integer("max_tokens").default(8000),
    temperature: integer("temperature").default(70), // stored as 70 = 0.70
    parentThreadId: uuid("parent_thread_id"),
    isArchived: boolean("is_archived").default(false),
    isPinned: boolean("is_pinned").default(false),
    agentTeamId: uuid("agent_team_id"),
    createdAt: timestamp("created_at", { withTimezone: true }).defaultNow(),
    updatedAt: timestamp("updated_at", { withTimezone: true }).defaultNow(),
  },
  (t) => [
    index("threads_workspace_idx").on(t.workspaceId),
    index("threads_created_at_idx").on(t.createdAt),
  ],
);

// ── Messages ───────────────────────────────────────────────────────────────

export const messages = pgTable(
  "messages",
  {
    id: uuid("id").defaultRandom().primaryKey(),
    threadId: uuid("thread_id")
      .notNull()
      .references(() => threads.id, { onDelete: "cascade" }),
    parentMessageId: uuid("parent_message_id"),
    role: messageRoleEnum("role").notNull(),
    content: text("content").notNull().default(""),
    reasoning: text("reasoning"),
    citations: jsonb("citations").$type<
      { source: string; excerpt: string; score: number }[]
    >(),
    isEdited: boolean("is_edited").default(false),
    isRegenerated: boolean("is_regenerated").default(false),
    branchId: uuid("branch_id"),
    sandboxId: text("sandbox_id"),
    tokenCount: integer("token_count"),
    cost: integer("cost"), // stored in micro-cents (1e-8 dollars)
    createdAt: timestamp("created_at", { withTimezone: true }).defaultNow(),
  },
  (t) => [
    index("messages_thread_idx").on(t.threadId),
    index("messages_created_at_idx").on(t.createdAt),
  ],
);

// ── Agent Steps ────────────────────────────────────────────────────────────

export const agentSteps = pgTable(
  "agent_steps",
  {
    id: uuid("id").defaultRandom().primaryKey(),
    messageId: uuid("message_id")
      .notNull()
      .references(() => messages.id, { onDelete: "cascade" }),
    stepType: agentStepTypeEnum("step_type").notNull(),
    status: agentStepStatusEnum("status").notNull().default("pending"),
    name: text("name").notNull(),
    displayName: text("display_name"),
    args: jsonb("args"),
    result: jsonb("result"),
    error: text("error"),
    agentName: text("agent_name"),
    capabilityToken: text("capability_token"),
    toolCallId: text("tool_call_id"),
    startedAt: timestamp("started_at", { withTimezone: true }),
    endedAt: timestamp("ended_at", { withTimezone: true }),
    createdAt: timestamp("created_at", { withTimezone: true }).defaultNow(),
  },
  (t) => [index("agent_steps_message_idx").on(t.messageId)],
);

// ── Canvas Tiles ───────────────────────────────────────────────────────────

export const canvasTiles = pgTable(
  "canvas_tiles",
  {
    id: uuid("id").defaultRandom().primaryKey(),
    threadId: uuid("thread_id")
      .notNull()
      .references(() => threads.id, { onDelete: "cascade" }),
    tileKind: tileKindEnum("tile_kind").notNull(),
    title: text("title"),
    layout: jsonb("layout").$type<{
      x: number;
      y: number;
      w: number;
      h: number;
      minW?: number;
      minH?: number;
      maxW?: number;
      maxH?: number;
    }>(),
    config: jsonb("config"),
    isMinimized: boolean("is_minimized").default(false),
    isPinned: boolean("is_pinned").default(false),
    sortOrder: integer("sort_order").default(0),
    createdAt: timestamp("created_at", { withTimezone: true }).defaultNow(),
    updatedAt: timestamp("updated_at", { withTimezone: true }).defaultNow(),
  },
  (t) => [index("canvas_tiles_thread_idx").on(t.threadId)],
);

// ── Tool Registry ──────────────────────────────────────────────────────────

export const toolDefinitions = pgTable("tool_definitions", {
  id: uuid("id").defaultRandom().primaryKey(),
  name: text("name").notNull().unique(),
  displayName: text("display_name").notNull(),
  description: text("description"),
  category: text("category").notNull().default("utility"),
  inputSchema: jsonb("input_schema"),
  requiredScopes: jsonb("required_scopes").$type<string[]>(),
  rateLimitPerMin: integer("rate_limit_per_min"),
  requiresSandbox: boolean("requires_sandbox").default(false),
  requiresApproval: boolean("requires_approval").default(false),
  isEnabled: boolean("is_enabled").default(true),
  createdAt: timestamp("created_at", { withTimezone: true }).defaultNow(),
});

export const workspaceToolPermissions = pgTable(
  "workspace_tool_permissions",
  {
    id: uuid("id").defaultRandom().primaryKey(),
    workspaceId: text("workspace_id").notNull(),
    toolId: uuid("tool_id")
      .notNull()
      .references(() => toolDefinitions.id, { onDelete: "cascade" }),
    isAllowed: boolean("is_allowed").default(true),
    grantedBy: text("granted_by"),
    grantedAt: timestamp("granted_at", { withTimezone: true }).defaultNow(),
  },
  (t) => [index("wtp_workspace_idx").on(t.workspaceId, t.toolId)],
);

// ── Sandboxes ──────────────────────────────────────────────────────────────

export const sandboxes = pgTable(
  "sandboxes",
  {
    id: uuid("id").defaultRandom().primaryKey(),
    sandboxType: text("sandbox_type").notNull().default("code"), // "code" | "browser"
    language: text("language").default("python"),
    threadId: uuid("thread_id").references(() => threads.id, {
      onDelete: "set null",
    }),
    messageId: uuid("message_id").references(() => messages.id, {
      onDelete: "set null",
    }),
    containerId: text("container_id"),
    previewUrl: text("preview_url"),
    previewToken: text("preview_token"),
    status: text("status").notNull().default("creating"), // creating|running|stopped|expired
    files: jsonb("files"),
    expiresAt: timestamp("expires_at", { withTimezone: true }),
    createdAt: timestamp("created_at", { withTimezone: true }).defaultNow(),
  },
  (t) => [index("sandboxes_thread_idx").on(t.threadId)],
);

// ── Agent Teams ────────────────────────────────────────────────────────────

export const agentTeams = pgTable("agent_teams", {
  id: uuid("id").defaultRandom().primaryKey(),
  name: text("name").notNull(),
  description: text("description"),
  members: jsonb("members").$type<
    { name: string; role: string; systemPrompt: string }[]
  >(),
  protocol: text("protocol").notNull().default("sequential"), // sequential|debate|swarm|escalation
  maxTurns: integer("max_turns").default(10),
  escalationPolicy: jsonb("escalation_policy"),
  createdAt: timestamp("created_at", { withTimezone: true }).defaultNow(),
});

// ── Prompt Versions ───────────────────────────────────────────────────────

export const promptVersions = pgTable(
  "prompt_versions",
  {
    id: uuid("id").defaultRandom().primaryKey(),
    name: text("name").notNull(),
    content: text("content").notNull(),
    version: integer("version").notNull().default(1),
    isActive: boolean("is_active").default(true),
    createdAt: timestamp("created_at", { withTimezone: true }).defaultNow(),
  },
  (t) => [index("prompt_versions_name_idx").on(t.name)],
);

// ── Branches ───────────────────────────────────────────────────────────────

export const branches = pgTable(
  "branches",
  {
    id: uuid("id").defaultRandom().primaryKey(),
    threadId: uuid("thread_id")
      .notNull()
      .references(() => threads.id, { onDelete: "cascade" }),
    parentMessageId: uuid("parent_message_id")
      .notNull()
      .references(() => messages.id, { onDelete: "cascade" }),
    title: text("title"),
    createdAt: timestamp("created_at", { withTimezone: true }).defaultNow(),
  },
  (t) => [index("branches_thread_idx").on(t.threadId)],
);

// ── Type exports ───────────────────────────────────────────────────────────

export type Thread = typeof threads.$inferSelect;
export type NewThread = typeof threads.$inferInsert;
export type Message = typeof messages.$inferSelect;
export type NewMessage = typeof messages.$inferInsert;
export type AgentStep = typeof agentSteps.$inferSelect;
export type NewAgentStep = typeof agentSteps.$inferInsert;
export type CanvasTile = typeof canvasTiles.$inferSelect;
export type NewCanvasTile = typeof canvasTiles.$inferInsert;
export type ToolDefinition = typeof toolDefinitions.$inferSelect;
export type Sandbox = typeof sandboxes.$inferSelect;
export type AgentTeam = typeof agentTeams.$inferSelect;
export type PromptVersion = typeof promptVersions.$inferSelect;
export type Branch = typeof branches.$inferSelect;
