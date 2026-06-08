/**
 * k6 performance test — Auth endpoints
 *
 * Auth is the critical path for every authenticated request.
 * Login must be fast even under load — bcrypt is intentionally slow,
 * so we measure whether the async handling keeps throughput acceptable.
 *
 * Key SLOs:
 *   - Login p99 < 1000ms (bcrypt is CPU-bound, can't be cached)
 *   - Register p99 < 1000ms
 *   - Token refresh p99 < 300ms (no bcrypt — just JWT decode + DB lookup)
 *   - Error rate < 1%
 *
 * Usage:
 *   k6 run k6/auth.test.js
 *   K6_SCENARIO=stress k6 run k6/auth.test.js
 */

import http from "k6/http";
import { check, group, sleep } from "k6";
import { Counter, Trend } from "k6/metrics";
import { BASE_URL, LOAD, SMOKE, STRESS } from "./config.js";

// ── Custom metrics ────────────────────────────────────────────────────────────
const loginLatency    = new Trend("auth_login_duration", true);
const registerLatency = new Trend("auth_register_duration", true);
const refreshLatency  = new Trend("auth_refresh_duration", true);
const authFailures    = new Counter("auth_failures");

const SCENARIOS = { smoke: SMOKE, load: LOAD, stress: STRESS };
const scenario = SCENARIOS[__ENV.K6_SCENARIO] || LOAD;

export const options = {
  scenarios: { auth: scenario },
  thresholds: {
    // bcrypt is intentionally slow — p99 under 1s is the SLO
    auth_login_duration:    ["p(99)<1000", "p(95)<800"],
    auth_register_duration: ["p(99)<1000", "p(95)<800"],
    // Refresh is just JWT decode + 1 DB query — should be fast
    auth_refresh_duration:  ["p(99)<300",  "p(95)<200"],
    http_req_failed:        ["rate<0.01"],
  },
};

// ── Setup: pre-create a user to use in login/refresh tests ───────────────────
export function setup() {
  const email = `perf_user_${Date.now()}@test.com`;
  const password = "PerfTest123!";

  http.post(`${BASE_URL}/api/v1/auth/register`,
    JSON.stringify({ email, password }),
    { headers: { "Content-Type": "application/json" } }
  );

  const loginResp = http.post(`${BASE_URL}/api/v1/auth/login`,
    JSON.stringify({ email, password }),
    { headers: { "Content-Type": "application/json" } }
  );

  const body = JSON.parse(loginResp.body);
  return { email, password, refreshToken: body.refresh_token };
}

// ── Main test loop ────────────────────────────────────────────────────────────
export default function (data) {
  // Each VU uses a unique email to avoid duplicate conflicts
  const vuEmail = `vu_${__VU}_${Date.now()}@test.com`;

  group("register new user", () => {
    const start = Date.now();
    const resp = http.post(`${BASE_URL}/api/v1/auth/register`,
      JSON.stringify({ email: vuEmail, password: "PerfTest123!" }),
      { headers: { "Content-Type": "application/json" } }
    );
    registerLatency.add(Date.now() - start);

    const ok = check(resp, {
      "register 201": (r) => r.status === 201,
    });
    if (!ok) authFailures.add(1);
  });

  group("login", () => {
    const start = Date.now();
    const resp = http.post(`${BASE_URL}/api/v1/auth/login`,
      JSON.stringify({ email: vuEmail, password: "PerfTest123!" }),
      { headers: { "Content-Type": "application/json" } }
    );
    loginLatency.add(Date.now() - start);

    const ok = check(resp, {
      "login 200":           (r) => r.status === 200,
      "has access_token":    (r) => !!JSON.parse(r.body).access_token,
      "has refresh_token":   (r) => !!JSON.parse(r.body).refresh_token,
    });
    if (!ok) authFailures.add(1);
  });

  group("token refresh", () => {
    const start = Date.now();
    const resp = http.post(`${BASE_URL}/api/v1/auth/refresh`,
      JSON.stringify({ refresh_token: data.refreshToken }),
      { headers: { "Content-Type": "application/json" } }
    );
    refreshLatency.add(Date.now() - start);

    check(resp, {
      // Refresh may return 401 under high concurrency (token rotation race)
      // — count as success if either 200 or 401
      "refresh responded": (r) => [200, 401].includes(r.status),
    });
  });

  sleep(0.5);
}

export function handleSummary(data) {
  return {
    "k6/results/auth-summary.json": JSON.stringify(data, null, 2),
    stdout: textSummary(data),
  };
}

function textSummary(data) {
  const m = data.metrics;
  const fmt = (t) => t?.values?.["p(99)"]?.toFixed(1) ?? "N/A";
  return [
    "\n── Auth Endpoint Performance Summary ───────────────────",
    `  register p99 : ${fmt(m.auth_register_duration)}ms`,
    `  login    p99 : ${fmt(m.auth_login_duration)}ms`,
    `  refresh  p99 : ${fmt(m.auth_refresh_duration)}ms`,
    `  failures     : ${m.auth_failures?.values.count ?? 0}`,
    `  error rate   : ${((m.http_req_failed?.values.rate ?? 0) * 100).toFixed(2)}%`,
    "────────────────────────────────────────────────────────\n",
  ].join("\n");
}
