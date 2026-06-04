/**
 * Flowmanner Load Test Configuration
 *
 * Shared config, auth helpers, and performance budgets for all k6 scripts.
 */

import http from "k6/http";
import { check, sleep } from "k6";
import { Rate, Trend, Counter } from "k6/metrics";

// ── Custom Metrics ─────────────────────────────────────────────────────────
export const errorRate = new Rate("errors");
export const authDuration = new Trend("auth_duration_ms", true);
export const apiDuration = new Trend("api_duration_ms", true);
export const missionCreateDuration = new Trend("mission_create_ms", true);
export const chatDuration = new Trend("chat_message_ms", true);
export const searchDuration = new Trend("search_ms", true);
export const requestCount = new Counter("total_requests");

// ── Environment ────────────────────────────────────────────────────────────
const BASE_URL = __ENV.BASE_URL || "http://127.0.0.1:8000";
const TEST_EMAIL = __ENV.TEST_EMAIL || "loadtest@example.com";
const TEST_PASSWORD = __ENV.TEST_PASSWORD || "LoadTest123!";

// ── Performance Budgets (ms) ───────────────────────────────────────────────
export const BUDGETS = {
  health: 200,
  login: 500,
  missionCreate: 2000,
  missionList: 500,
  chatMessage: 500,
  search: 1000,
  apiGeneric: 500,
};

// ── Default Options ────────────────────────────────────────────────────────
export const baseOptions = {
  thresholds: {
    http_req_duration: ["p(95)<500", "p(99)<1000"],
    errors: ["rate<0.05"],
    auth_duration_ms: ["p(95)<500"],
    api_duration_ms: ["p(95)<500"],
  },
  noConnectionReuse: false,
  userAgent: "FlowmannerLoadTest/1.0",
};

// ── Auth Helper ────────────────────────────────────────────────────────────

/**
 * Login and return JWT access token.
 * Registers the user first if they don't exist.
 */
export function getAuthToken() {
  // Try login first
  const loginRes = http.post(
    `${BASE_URL}/api/auth/login`,
    JSON.stringify({
      username_or_email: TEST_EMAIL,
      password: TEST_PASSWORD,
    }),
    { headers: { "Content-Type": "application/json" } }
  );

  if (loginRes.status === 200) {
    const body = loginRes.json();
    authDuration.add(loginRes.timings.duration);
    return body.access_token || body.token;
  }

  // Register if login failed (user doesn't exist)
  const regRes = http.post(
    `${BASE_URL}/api/auth/register`,
    JSON.stringify({
      email: TEST_EMAIL,
      password: TEST_PASSWORD,
      full_name: "Load Test User",
      username: "loadtestuser",
    }),
    { headers: { "Content-Type": "application/json" } }
  );

  if (regRes.status === 201 || regRes.status === 200) {
    const body = regRes.json();
    authDuration.add(regRes.timings.duration);
    return body.access_token || body.token;
  }

  console.error(`Auth failed: login=${loginRes.status}, register=${regRes.status}`);
  return null;
}

/**
 * Create auth headers for a given token.
 */
export function authHeaders(token) {
  return {
    "Content-Type": "application/json",
    Authorization: `Bearer ${token}`,
  };
}

// ── Setup Helper ───────────────────────────────────────────────────────────

/**
 * Shared setup: authenticate and return token + workspace info.
 */
export function setupAuth() {
  const token = getAuthToken();
  if (!token) {
    throw new Error("Failed to authenticate — cannot run load test");
  }

  // Get user's workspace
  const userRes = http.get(`${BASE_URL}/api/users/me`, {
    headers: authHeaders(token),
  });

  let workspaceId = null;
  if (userRes.status === 200) {
    const user = userRes.json();
    workspaceId = user.workspace_id || user.default_workspace_id;
  }

  return { token, workspaceId };
}

// ── Check Helpers ──────────────────────────────────────────────────────────

/**
 * Standard success check with error rate tracking.
 */
export function checkRes(res, name, expectedStatus) {
  const ok = check(res, {
    [`${name} status ${expectedStatus}`]: (r) => r.status === expectedStatus,
    [`${name} duration < budget`]: (r) => r.timings.duration < (BUDGETS[name] || BUDGETS.apiGeneric),
  });

  errorRate.add(!ok);
  requestCount.add(1);
  apiDuration.add(res.timings.duration);
  return ok;
}
