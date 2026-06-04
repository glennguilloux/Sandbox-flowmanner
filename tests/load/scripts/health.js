/**
 * Health & Readiness Load Test
 *
 * Tests the health endpoint under sustained load.
 * This is the lightest test — establishes baseline throughput.
 */

import http from "k6/http";
import { check, sleep } from "k6";
import { Rate, Trend } from "k6/metrics";
import { baseOptions, checkRes, BUDGETS } from "../config.js";

const healthDuration = new Trend("health_duration_ms", true);
const errorRate = new Rate("errors");

export const options = {
  ...baseOptions,
  scenarios: {
    health_smoke: {
      executor: "constant-vus",
      vus: 10,
      duration: "30s",
      tags: { test_type: "smoke" },
    },
    health_load: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: "20s", target: 50 },
        { duration: "40s", target: 100 },
        { duration: "20s", target: 0 },
      ],
      startTime: "35s",
      tags: { test_type: "load" },
    },
    health_stress: {
      executor: "ramping-arrival-rate",
      startRate: 50,
      timeUnit: "1s",
      preAllocatedVUs: 200,
      stages: [
        { duration: "30s", target: 200 },
        { duration: "30s", target: 500 },
        { duration: "20s", target: 0 },
      ],
      startTime: "120s",
      tags: { test_type: "stress" },
    },
  },
  thresholds: {
    ...baseOptions.thresholds,
    health_duration_ms: [`p(95)<${BUDGETS.health}`],
  },
};

export default function () {
  const res = http.get("http://127.0.0.1:8000/api/health");
  checkRes(res, "health", 200);
  healthDuration.add(res.timings.duration);
  sleep(0.1);
}
