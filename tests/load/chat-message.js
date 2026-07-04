import http from "k6/http";
import { check, sleep } from "k6";
import { Counter } from "k6/metrics";

const BASE_URL = __ENV.BASE_URL || "http://localhost:8000";
const AUTH_TOKEN = __ENV.AUTH_TOKEN || "";

const chat_requests = new Counter("chat_requests");

export const options = {
  stages: [
    { duration: "20s", target: 3 },   // ramp up (lower concurrency — streaming is long-lived)
    { duration: "1m", target: 3 },    // sustain
    { duration: "20s", target: 0 },   // ramp down
  ],
  thresholds: {
    http_req_duration: ["p(95)<30000"],  // streaming can take up to 30s
    http_req_failed: ["rate<0.1"],
  },
};

const headers = {
  "Content-Type": "application/json",
  ...(AUTH_TOKEN ? { Authorization: `Bearer ${AUTH_TOKEN}` } : {}),
};

export default function () {
  // 1. List chat threads to find an existing one
  const threadsRes = http.get(
    `${BASE_URL}/api/v2/chat/threads?per_page=1`,
    { headers }
  );

  let threadId = null;
  if (threadsRes.status === 200) {
    const body = threadsRes.json();
    const items = body?.data?.items || body?.items || [];
    if (items.length > 0) {
      threadId = items[0].id;
    }
  }

  // 2. Create a thread if none exists
  if (!threadId) {
    const createRes = http.post(
      `${BASE_URL}/api/v2/chat/threads`,
      JSON.stringify({ title: `k6-thread-${Date.now()}` }),
      { headers }
    );
    if (createRes.status === 201 || createRes.status === 200) {
      threadId = createRes.json("data?.id") || createRes.json("id");
    }
  }

  if (!threadId) return;

  // 3. Send a chat message (non-streaming for load test simplicity)
  const chatRes = http.post(
    `${BASE_URL}/api/v2/chat/threads/${threadId}/chat`,
    JSON.stringify({
      content: "Hello, this is a load test message. Respond briefly.",
    }),
    { headers, timeout: "30s" }
  );

  check(chatRes, {
    "chat response received": (r) => r.status === 200,
  });
  chat_requests.add(1);

  sleep(2);
}
