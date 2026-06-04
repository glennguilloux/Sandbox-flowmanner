/**
 * Chat / LLM Load Test
 *
 * Tests chat thread creation and message sending.
 * Message sending triggers LLM calls — the most expensive operation.
 * Uses streaming endpoint for realistic load.
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

const threadCreateDur = new Trend("chat_thread_create_ms", true);
const messageDur = new Trend("chat_message_ms", true);
const errorRate = new Rate("errors");

export const options = {
  ...baseOptions,
  scenarios: {
    chat_smoke: {
      executor: "constant-vus",
      vus: 2,
      duration: "30s",
      tags: { test_type: "smoke" },
    },
    chat_load: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: "20s", target: 5 },
        { duration: "40s", target: 10 },
        { duration: "20s", target: 0 },
      ],
      startTime: "35s",
      tags: { test_type: "load" },
    },
  },
  thresholds: {
    ...baseOptions.thresholds,
    chat_message_ms: [`p(95)<${BUDGETS.chatMessage}`],
  },
};

const BASE_URL = __ENV.BASE_URL || "http://127.0.0.1:8000";

export function setup() {
  return setupAuth();
}

export default function (data) {
  const { token } = data;
  const headers = authHeaders(token);

  // ── Create Thread ──────────────────────────────────────────────────────
  const threadRes = http.post(
    `${BASE_URL}/api/chat/threads`,
    JSON.stringify({
      title: `Load Test Thread ${Date.now()}`,
    }),
    { headers }
  );

  const threadOk = check(threadRes, {
    "thread create status 201": (r) => r.status === 201 || r.status === 200,
  });

  threadCreateDur.add(threadRes.timings.duration);
  errorRate.add(!threadOk);

  if (!threadOk) {
    sleep(1);
    return;
  }

  let threadId;
  try {
    threadId = threadRes.json().id;
  } catch {
    sleep(1);
    return;
  }

  // ── Send Message (non-streaming for load test) ─────────────────────────
  const msgRes = http.post(
    `${BASE_URL}/api/chat/threads/${threadId}/messages`,
    JSON.stringify({
      role: "user",
      content: "Hello, this is a load test message. Reply briefly.",
    }),
    { headers }
  );

  const msgOk = check(msgRes, {
    "message status 200/201": (r) => r.status === 200 || r.status === 201,
    [`message < ${BUDGETS.chatMessage}ms`]: (r) => r.timings.duration < BUDGETS.chatMessage,
  });

  messageDur.add(msgRes.timings.duration);
  errorRate.add(!msgOk);

  // ── List Messages ──────────────────────────────────────────────────────
  const listRes = http.get(
    `${BASE_URL}/api/chat/threads/${threadId}/messages`,
    { headers }
  );
  checkRes(listRes, "apiGeneric", 200);

  sleep(2);
}
