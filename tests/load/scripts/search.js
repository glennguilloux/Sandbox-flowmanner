/**
 * Search Load Test
 *
 * Tests search endpoint under concurrent queries.
 * Search hits PostgreSQL + potentially Qdrant for vector search.
 */

import http from "k6/http";
import { check, sleep } from "k6";
import { Rate, Trend } from "k6/metrics";
import {
  baseOptions,
  setupAuth,
  authHeaders,
  checkRes,
  BUDGETS,
} from "../config.js";

const searchDur = new Trend("search_ms", true);
const suggestionsDur = new Trend("search_suggestions_ms", true);
const errorRate = new Rate("errors");

const SEARCH_TERMS = [
  "test",
  "mission",
  "agent",
  "workflow",
  "chat",
  "deploy",
  "api",
  "database",
  "user",
  "config",
];

export const options = {
  ...baseOptions,
  scenarios: {
    search_smoke: {
      executor: "constant-vus",
      vus: 5,
      duration: "30s",
      tags: { test_type: "smoke" },
    },
    search_load: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: "20s", target: 20 },
        { duration: "40s", target: 50 },
        { duration: "20s", target: 0 },
      ],
      startTime: "35s",
      tags: { test_type: "load" },
    },
  },
  thresholds: {
    ...baseOptions.thresholds,
    search_ms: [`p(95)<${BUDGETS.search}`],
  },
};

const BASE_URL = __ENV.BASE_URL || "http://127.0.0.1:8000";

export function setup() {
  return setupAuth();
}

export default function (data) {
  const { token } = data;
  const headers = authHeaders(token);
  const query = SEARCH_TERMS[Math.floor(Math.random() * SEARCH_TERMS.length)];

  // ── Full Search ────────────────────────────────────────────────────────
  const searchRes = http.get(
    `${BASE_URL}/api/search?q=${query}&type=missions,agents&limit=20`,
    { headers }
  );

  const searchOk = check(searchRes, {
    "search status 200": (r) => r.status === 200,
    [`search < ${BUDGETS.search}ms`]: (r) => r.timings.duration < BUDGETS.search,
  });

  searchDur.add(searchRes.timings.duration);
  errorRate.add(!searchOk);

  // ── Suggestions ────────────────────────────────────────────────────────
  const sugRes = http.get(
    `${BASE_URL}/api/search/suggestions?q=${query}`,
    { headers }
  );

  checkRes(sugRes, "apiGeneric", 200);
  suggestionsDur.add(sugRes.timings.duration);

  sleep(0.5);
}
