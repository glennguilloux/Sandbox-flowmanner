/**
 * Authentication Load Test
 *
 * Tests login endpoint under concurrent load.
 * Uses shared credentials — rate limit aware (5 req/min per IP).
 * Adjust VUs to stay under rate limits or set RATE_LIMIT_DISABLED=true for stress testing.
 */

import http from "k6/http";
import { check, sleep } from "k6";
import { Rate, Trend } from "k6/metrics";
import {
  baseOptions,
  getAuthToken,
  authHeaders,
  checkRes,
  BUDGETS,
} from "../config.js";

const loginDuration = new Trend("login_duration_ms", true);
const errorRate = new Rate("errors");

// Rate limit: 5 req/min per IP — single VU, 15s between requests
export const options = {
  ...baseOptions,
  scenarios: {
    login_smoke: {
      executor: "constant-vus",
      vus: 1,
      duration: "60s",
      tags: { test_type: "smoke" },
    },
  },
  thresholds: {
    // Rate-limit 429s are expected — only check latency of successful logins
    http_req_duration: ["p(95)<500"],
    login_duration_ms: [`p(95)<${BUDGETS.login}`],
  },
};

const BASE_URL = __ENV.BASE_URL || "http://127.0.0.1:8000";
const TEST_EMAIL = __ENV.TEST_EMAIL || "loadtest@example.com";
const TEST_PASSWORD = __ENV.TEST_PASSWORD || "LoadTest123!";

export default function () {
  // Login
  const loginRes = http.post(
    `${BASE_URL}/api/auth/login`,
    JSON.stringify({
      username_or_email: TEST_EMAIL,
      password: TEST_PASSWORD,
    }),
    { headers: { "Content-Type": "application/json" } }
  );

  const loginOk = check(loginRes, {
    "login status 200": (r) => r.status === 200,
    "login has token": (r) => {
      try {
        const body = r.json();
        return !!(body.access_token || body.token);
      } catch {
        return false;
      }
    },
    [`login < ${BUDGETS.login}ms`]: (r) => r.timings.duration < BUDGETS.login,
  });

  loginDuration.add(loginRes.timings.duration);
  errorRate.add(!loginOk);

  if (!loginOk) {
    sleep(1);
    return;
  }

  const token = loginRes.json().access_token || loginRes.json().token;

  // Validate token with /users/me
  const meRes = http.get(`${BASE_URL}/api/users/me`, {
    headers: authHeaders(token),
  });

  checkRes(meRes, "apiGeneric", 200);
  // Sleep 15s to stay under 5 req/min rate limit
  sleep(15);
}
