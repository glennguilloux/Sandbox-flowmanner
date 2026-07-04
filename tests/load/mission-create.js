import http from "k6/http";
import { check, sleep } from "k6";
import { Counter } from "k6/metrics";

const BASE_URL = __ENV.BASE_URL || "http://localhost:8000";
const AUTH_TOKEN = __ENV.AUTH_TOKEN || "";

const missions_created = new Counter("missions_created");

export const options = {
  stages: [
    { duration: "30s", target: 5 },   // ramp up
    { duration: "1m", target: 5 },    // sustain
    { duration: "30s", target: 0 },   // ramp down
  ],
  thresholds: {
    http_req_duration: ["p(95)<2000"],  // 95% under 2s
    http_req_failed: ["rate<0.1"],      // <10% errors
  },
};

const headers = {
  "Content-Type": "application/json",
  ...(AUTH_TOKEN ? { Authorization: `Bearer ${AUTH_TOKEN}` } : {}),
};

export default function () {
  // 1. Create a mission
  const createRes = http.post(
    `${BASE_URL}/api/v2/missions`,
    JSON.stringify({
      title: `k6-load-test-${Date.now()}`,
      description: "Load test mission",
      mission_type: "solo",
    }),
    { headers }
  );

  check(createRes, {
    "mission created": (r) => r.status === 201 || r.status === 200,
  });

  if (createRes.status === 201 || createRes.status === 200) {
    missions_created.add(1);
    const missionId = createRes.json("data?.id") || createRes.json("id");

    // 2. Get mission details
    const getRes = http.get(`${BASE_URL}/api/v2/missions/${missionId}`, { headers });
    check(getRes, { "mission fetched": (r) => r.status === 200 });

    // 3. List missions (dashboard query)
    const listRes = http.get(`${BASE_URL}/api/v2/missions?per_page=20`, { headers });
    check(listRes, { "missions listed": (r) => r.status === 200 });
  }

  sleep(1);
}
