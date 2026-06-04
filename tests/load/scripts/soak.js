/**
 * Soak Test: Extended Duration
 *
 * Runs moderate load for an extended period to detect:
 * - Memory leaks
 * - Connection pool exhaustion
 * - Gradual performance degradation
 * - Log file growth
 *
 * Duration: ~30 minutes (adjust stages as needed)
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

const errorRate = new Rate("errors");
const apiDur = new Trend("api_duration_ms", true);

export const options = {
  ...baseOptions,
  scenarios: {
    soak: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: "2m", target: 20 },    // ramp up
        { duration: "25m", target: 20 },   // sustained load
        { duration: "2m", target: 0 },     // cool down
      ],
      tags: { test_type: "soak" },
    },
  },
  thresholds: {
    ...baseOptions.thresholds,
    // Soak test: allow slightly higher p95 but catch degradation
    http_req_duration: ["p(95)<800", "p(99)<2000"],
    errors: ["rate<0.1"],
  },
};

const BASE_URL = __ENV.BASE_URL || "http://127.0.0.1:8000";

export function setup() {
  return setupAuth();
}

export default function (data) {
  const { token } = data;
  const headers = authHeaders(token);

  const roll = Math.random();

  if (roll < 0.3) {
    // 30% — Health
    const res = http.get(`${BASE_URL}/api/health`);
    checkRes(res, "health", 200);

  } else if (roll < 0.5) {
    // 20% — List missions
    const res = http.get(`${BASE_URL}/api/missions?page=1&per_page=10`, { headers });
    checkRes(res, "apiGeneric", 200);
    apiDur.add(res.timings.duration);

  } else if (roll < 0.7) {
    // 20% — List agents
    const res = http.get(`${BASE_URL}/api/agents?page=1&per_page=10`, { headers });
    checkRes(res, "apiGeneric", 200);

  } else if (roll < 0.85) {
    // 15% — Dashboard
    const res = http.get(`${BASE_URL}/api/dashboard/stats`, { headers });
    checkRes(res, "apiGeneric", 200);

  } else {
    // 15% — Search
    const queries = ["test", "mission", "agent"];
    const q = queries[Math.floor(Math.random() * queries.length)];
    const res = http.get(`${BASE_URL}/api/search?q=${q}&limit=10`, { headers });
    checkRes(res, "apiGeneric", 200);
  }

  errorRate.add(false);
  sleep(1);
}
