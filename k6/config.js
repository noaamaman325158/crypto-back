/**
 * Shared configuration and helpers for all k6 performance tests.
 *
 * Thresholds are the SLOs (Service Level Objectives) we enforce:
 * - p99 < 500ms for read endpoints (cached responses should be fast)
 * - p99 < 1000ms for write endpoints (DB writes, external API calls)
 * - error rate < 1% (excluding expected 429 rate-limit responses)
 * - throughput: defined per scenario
 */

export const BASE_URL = __ENV.BASE_URL || "http://localhost:8000";
export const INTERNAL_API_KEY = __ENV.INTERNAL_API_KEY || "dev-internal-key";

// ── Global SLO thresholds ─────────────────────────────────────────────────────
export const THRESHOLDS = {
  // p99 for all HTTP requests must be under 500ms
  http_req_duration: ["p(99)<500", "p(95)<300", "p(50)<100"],

  // Error rate: less than 1% of requests may fail
  // (429 Too Many Requests is excluded — it's expected under load)
  http_req_failed: ["rate<0.01"],

  // Throughput: at least 50 requests/sec sustained
  http_reqs: ["rate>50"],
};

// ── Scenario: smoke test — 1 VU, 30s ─────────────────────────────────────────
// Verifies the system is functional under minimal load.
export const SMOKE = {
  executor: "constant-vus",
  vus: 1,
  duration: "30s",
};

// ── Scenario: load test — ramp up to 50 VU ────────────────────────────────────
// Simulates normal production traffic.
export const LOAD = {
  executor: "ramping-vus",
  stages: [
    { duration: "30s", target: 10 },  // warm up
    { duration: "1m",  target: 50 },  // sustained load
    { duration: "30s", target: 0  },  // ramp down
  ],
};

// ── Scenario: stress test — ramp to 200 VU ───────────────────────────────────
// Finds the breaking point — where errors start or latency degrades past SLO.
export const STRESS = {
  executor: "ramping-vus",
  stages: [
    { duration: "30s", target: 50  },
    { duration: "1m",  target: 100 },
    { duration: "1m",  target: 200 },
    { duration: "30s", target: 0   },
  ],
};

// ── Scenario: spike test — instant jump to 500 VU ────────────────────────────
// Simulates a sudden traffic burst (viral event, market crash, etc.)
export const SPIKE = {
  executor: "ramping-vus",
  stages: [
    { duration: "10s", target: 500 },  // spike
    { duration: "1m",  target: 500 },  // sustain
    { duration: "10s", target: 0   },  // drop
  ],
};

// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Register a user and return their JWT access token.
 * Called in setup() so tokens are pre-created before the test loop.
 */
export function getToken(email, password = "Password123!") {
  const http = require("k6/http");

  http.post(`${BASE_URL}/api/v1/auth/register`,
    JSON.stringify({ email, password }),
    { headers: { "Content-Type": "application/json" } }
  );

  const loginResp = http.post(`${BASE_URL}/api/v1/auth/login`,
    JSON.stringify({ email, password }),
    { headers: { "Content-Type": "application/json" } }
  );

  return JSON.parse(loginResp.body).access_token;
}

export function authHeaders(token) {
  return {
    "Authorization": `Bearer ${token}`,
    "Content-Type": "application/json",
  };
}

export function jsonHeaders() {
  return { "Content-Type": "application/json" };
}
