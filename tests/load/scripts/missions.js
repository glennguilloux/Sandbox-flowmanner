/**
 * Mission CRUD Load Test
 *
 * Tests mission creation, listing, and retrieval under load.
 * Mission creation triggers LLM planning — expensive endpoint.
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

const missionCreateDur = new Trend("mission_create_ms", true);
const missionListDur = new Trend("mission_list_ms", true);
const missionGetDur = new Trend("mission_get_ms", true);
const errorRate = new Rate("errors");

export const options = {
  ...baseOptions,
  scenarios: {
    mission_smoke: {
      executor: "constant-vus",
      vus: 3,
      duration: "30s",
      tags: { test_type: "smoke" },
    },
    mission_load: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: "20s", target: 10 },
        { duration: "40s", target: 25 },
        { duration: "20s", target: 0 },
      ],
      startTime: "35s",
      tags: { test_type: "load" },
    },
  },
  thresholds: {
    ...baseOptions.thresholds,
    mission_create_ms: [`p(95)<${BUDGETS.missionCreate}`],
    mission_list_ms: [`p(95)<${BUDGETS.missionList}`],
  },
};

const BASE_URL = __ENV.BASE_URL || "http://127.0.0.1:8000";

export function setup() {
  return setupAuth();
}

export default function (data) {
  const { token, workspaceId } = data;
  const headers = authHeaders(token);

  // ── List Missions ──────────────────────────────────────────────────────
  const listRes = http.get(`${BASE_URL}/api/missions?page=1&per_page=20`, { headers });
  const listOk = checkRes(listRes, "apiGeneric", 200);
  missionListDur.add(listRes.timings.duration);

  // ── Create Mission ─────────────────────────────────────────────────────
  const createRes = http.post(
    `${BASE_URL}/api/missions/`,
    JSON.stringify({
      title: `Load Test Mission ${Date.now()}`,
      description: "Auto-generated mission for load testing",
      mission_type: "simple",
    }),
    { headers }
  );

  const createOk = check(createRes, {
    "mission create status 201": (r) => r.status === 201 || r.status === 200,
    [`mission create < ${BUDGETS.missionCreate}ms`]: (r) =>
      r.timings.duration < BUDGETS.missionCreate,
  });

  missionCreateDur.add(createRes.timings.duration);
  errorRate.add(!createOk);

  // ── Get Created Mission ────────────────────────────────────────────────
  if (createOk) {
    try {
      const mission = createRes.json();
      const missionId = mission.id;
      if (missionId) {
        const getRes = http.get(`${BASE_URL}/api/missions/${missionId}`, { headers });
        checkRes(getRes, "apiGeneric", 200);
        missionGetDur.add(getRes.timings.duration);
      }
    } catch (e) {
      // Response may not be JSON
    }
  }

  sleep(1);
}
