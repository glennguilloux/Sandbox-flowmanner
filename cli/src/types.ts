/**
 * Public response shapes returned by the v2 API. These mirror the
 * Pydantic schemas in backend/app/schemas/blueprint.py and are used
 * by the command modules to type-check API responses.
 */

export interface BlueprintSummary {
  id: string;
  workspace_id?: string | null;
  user_id: number;
  title: string;
  description: string;
  blueprint_type: string;
  definition: Record<string, unknown>;
  input_schema?: Record<string, unknown> | null;
  output_schema?: Record<string, unknown> | null;
  status: string;
  version: number;
  tags?: string[] | null;
  category?: string | null;
  icon?: string | null;
  run_count: number;
  last_run_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface RunSummary {
  id: string;
  blueprint_id?: string | null;
  workspace_id?: string | null;
  user_id?: number | null;
  status: string;
  snapshot: Record<string, unknown>;
  output_data?: Record<string, unknown> | null;
  error_message?: string | null;
  total_tokens: number;
  total_cost_usd: number;
  budget_limit_usd?: number | null;
  started_at?: string | null;
  completed_at?: string | null;
  parent_run_id?: string | null;
  input_data?: Record<string, unknown> | null;
  meta?: Record<string, unknown> | null;
  created_at?: string | null;
  updated_at?: string | null;
}

/**
 * Substrate event record. Mirrors backend/app/schemas/blueprint.py
 * `RunEventResponse`: `timestamp` (not `created_at`), `actor` required,
 * `task_id` + `causal_parent` for audit / DAG correlation.
 */
export interface RunEvent {
  id: string;
  sequence: number;
  run_id: string;
  mission_id?: string | null;
  type: string;
  payload?: Record<string, unknown>;
  actor: string;
  task_id?: string | null;
  causal_parent?: number | null;
  timestamp?: string | null;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
}

export interface AuthTokens {
  access_token: string;
  refresh_token?: string;
  token_type?: string;
}

export interface UserSummary {
  id: number;
  email: string;
  username?: string | null;
  full_name?: string | null;
  role?: string;
  workspace_id?: string | null;
}
