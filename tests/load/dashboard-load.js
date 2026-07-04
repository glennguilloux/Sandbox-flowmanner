import http from "k6/http";
import { check, sleep, group } from "k6";
import { Counter } from "k6/metrics";

const BASE_URL = __ENV.BASE_URL || "http://localhost:8000";
const AUTH_TOKEN = __ENV.AUTH_TOKEN || "";

const api_calls = new Counter("api_calls");

export const options = {
  stages: [
    { duration: "30s", target: 10 },  // ramp up to 10 VUs
    { duration: "2m", target: 10 },   // sustain
    { duration: "30s", target: 0 },   // ramp down
  ],
  thresholds: {
    http_req_duration: ["p(95)<1000"],  // 95% under 1s
    http_req_failed: ["rate<0.05"],     // <5% errors
  },
};

const headers = {
  "Content-Type": "application/json",
  ...(AUTH_TOKEN ? { Authorization: `Bearer ${AUTH_TOKEN}` } : {}),
};

export default function () {
  // Simulate a dashboard page load — hits multiple API endpoints in parallel
  group("dashboard_load", function () {
    // 1. Health check (unauthenticated)
    const healthRes = http.get(`${BASE_URL}/api/health`);
    check(healthRes, { "health ok": (r) => r.status === 200 });
    api_calls.add(1);

    // 2. List missions
    group("missions_list", function () {
      const res = http.get(`${BASE_URL}/api/v2/missions?per_page=20`, { headers });
      check(res, { "missions loaded": (r) => r.status === 200 });
      api_calls.add(1);
    });

    // 3. List chat threads
    group("threads_list", function () {
      const res = http.get(`${BASE_URL}/api/v2/chat/threads?per_page=10`, { headers });
      check(res, { "threads loaded": (r) => r.status === 200 });
      api_calls.add(1);
    });

    // 4. List agents
    group("agents_list", function () {
      const res = http.get(`${BASE_URL}/api/v2/agents?per_page=10`, { headers });
      check(res, { "agents loaded": (r) => r.status === 200 });
      api_calls.add(1);
    });

    // 5. List templates
    group("templates_list", function () {
      const res = http.get(`${BASE_URL}/api/templates`, { headers });
      check(res, { "templates loaded": (r) => r.status === 200 });
      api_calls.add(1);
    });
  });

  sleep(2);
}
