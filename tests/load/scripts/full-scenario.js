/**
 * Full Scenario: Combined Load Test
 *
 * Runs all critical paths in a single mixed workload.
 * Simulates realistic user behavior across multiple endpoints.
 */

import http from "k6/http";
import { check, sleep } from "k6";
import { Rate, Trend, Counter } from "k6/metrics";
import {
  baseOptions,
  setupAuth,
  authHeaders,
  checkRes,
  BUDGETS,
} from "../config.js";

const errorRate = new Rate("errors");
const totalRequests = new Counter("total_requests");
const healthDur = new Trend("health_duration_ms", true);
const loginDur = new Trend("login_duration_ms", true);
const missionDur = new Trend("mission_create_ms", true);
const searchDur = new Trend("search_ms", true);
const chatDur = new Trend("chat_message_ms", true);

export const options = {
  ...baseOptions,
  scenarios: {
    full_load: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: "30s", target: 20 },   // ramp up
        { duration: "60s", target: 50 },   // sustained load
        { duration: "30s", target: 100 },  // stress
        { duration: "30s", target: 0 },    // cool down
      ],
      tags: { test_type: "full_scenario" },
    },
  },
  thresholds: {
    ...baseOptions.thresholds,
    health_duration_ms: [`p(95)<${BUDGETS.health}`],
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

  // Randomly pick an action weighted by typical usage
  const roll = Math.random();

  if (roll < 0.15) {
    // 15% — Health check
    const res = http.get(`${BASE_URL}/api/health`);
    checkRes(res, "health", 200);
    healthDur.add(res.timings.duration);

  } else if (roll < 0.25) {
    // 10% — Search
    const queries = ["test", "mission", "agent", "workflow", "chat"];
    const q = queries[Math.floor(Math.random() * queries.length)];
    const res = http.get(`${BASE_URL}/api/search?q=${q}&limit=10`, { headers });
    checkRes(res, "apiGeneric", 200);
    searchDur.add(res.timings.duration);

  } else if (roll < 0.40) {
    // 15% — List missions
    const res = http.get(`${BASE_URL}/api/missions?page=1&per_page=20`, { headers });
    checkRes(res, "apiGeneric", 200);

  } else if (roll < 0.50) {
    // 10% — Create mission
    const res = http.post(
      `${BASE_URL}/api/missions/`,
      JSON.stringify({
        title: `Full Scenario Mission ${Date.now()}`,
        description: "Auto-generated for full scenario load test",
        mission_type: "simple",
      }),
      { headers }
    );
    check(res, {
      "mission create 201": (r) => r.status === 201 || r.status === 200,
    });
    missionDur.add(res.timings.duration);

  } else if (roll < 0.60) {
    // 10% — List chat threads
    const res = http.get(`${BASE_URL}/api/chat/threads`, { headers });
    checkRes(res, "apiGeneric", 200);

  } else if (roll < 0.70) {
    // 10% — Dashboard stats
    const res = http.get(`${BASE_URL}/api/dashboard/stats`, { headers });
    checkRes(res, "apiGeneric", 200);

  } else if (roll < 0.80) {
    // 10% — List agents
    const res = http.get(`${BASE_URL}/api/agents?page=1&per_page=20`, { headers });
    checkRes(res, "apiGeneric", 200);

  } else {
    // 20% — Health + ready
    const h = http.get(`${BASE_URL}/api/health`);
    checkRes(h, "health", 200);
    const r = http.get(`${BASE_URL}/api/ready`);
    checkRes(r, "apiGeneric", 200);
  }

  totalRequests.add(1);
  sleep(Math.random() * 2 + 0.5); // 0.5-2.5s think time
}
