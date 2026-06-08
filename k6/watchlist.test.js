/**
 * k6 performance test — Watchlist endpoints (authenticated write path)
 *
 * This is the most complex flow: requires auth token + DB writes.
 * Tests the full user journey under load:
 *   login → add coin → read watchlist → remove coin
 *
 * Key SLOs:
 *   - Watchlist GET p99 < 300ms (DB query, not cached)
 *   - Watchlist POST p99 < 500ms (DB write with unique constraint check)
 *   - Throughput > 20 req/s sustained
 *
 * Usage:
 *   k6 run k6/watchlist.test.js
 *   K6_SCENARIO=stress k6 run k6/watchlist.test.js
 */

import http from "k6/http";
import { check, group, sleep } from "k6";
import { Trend, Rate } from "k6/metrics";
import { BASE_URL, INTERNAL_API_KEY, LOAD, SMOKE, STRESS } from "./config.js";

// ── Custom metrics ────────────────────────────────────────────────────────────
const watchlistGetLatency  = new Trend("watchlist_get_duration",  true);
const watchlistAddLatency  = new Trend("watchlist_add_duration",  true);
const watchlistDelLatency  = new Trend("watchlist_del_duration",  true);
const addSuccessRate       = new Rate("watchlist_add_success");

const SCENARIOS = { smoke: SMOKE, load: LOAD, stress: STRESS };
const scenario = SCENARIOS[__ENV.K6_SCENARIO] || LOAD;

export const options = {
  scenarios: { watchlist: scenario },
  thresholds: {
    watchlist_get_duration: ["p(99)<300", "p(95)<200"],
    watchlist_add_duration: ["p(99)<500", "p(95)<350"],
    watchlist_del_duration: ["p(99)<300", "p(95)<200"],
    watchlist_add_success:  ["rate>0.95"],
    http_req_failed:        ["rate<0.01"],
  },
};

// ── Setup: seed coins + create per-VU users ───────────────────────────────────
export function setup() {
  // Seed coin data
  http.post(`${BASE_URL}/api/v1/cryptocurrencies/refresh`, null, {
    headers: { "X-API-Key": INTERNAL_API_KEY },
  });

  // Get coin IDs to use in watchlist operations
  const listResp = http.get(`${BASE_URL}/api/v1/cryptocurrencies?per_page=10`);
  const coins = JSON.parse(listResp.body).data || [];

  return { coins: coins.map((c) => c.id) };
}

// ── Main test loop ────────────────────────────────────────────────────────────
export default function (data) {
  if (!data.coins?.length) return;

  const email = `wl_vu_${__VU}@perftest.com`;
  const password = "PerfTest123!";

  // Register (idempotent — will 409 on subsequent iterations, that's fine)
  http.post(`${BASE_URL}/api/v1/auth/register`,
    JSON.stringify({ email, password }),
    { headers: { "Content-Type": "application/json" } }
  );

  // Login — always fresh token
  const loginResp = http.post(`${BASE_URL}/api/v1/auth/login`,
    JSON.stringify({ email, password }),
    { headers: { "Content-Type": "application/json" } }
  );

  const token = JSON.parse(loginResp.body).access_token;
  if (!token) return;

  const headers = {
    "Authorization": `Bearer ${token}`,
    "Content-Type": "application/json",
  };

  // Pick a random coin for this iteration
  const coinId = data.coins[Math.floor(Math.random() * data.coins.length)];

  group("get watchlist", () => {
    const start = Date.now();
    const resp = http.get(`${BASE_URL}/api/v1/watchlist`, { headers });
    watchlistGetLatency.add(Date.now() - start);

    check(resp, {
      "get watchlist 200":  (r) => r.status === 200,
      "has items field":    (r) => JSON.parse(r.body).items !== undefined,
    });
  });

  group("add to watchlist", () => {
    const start = Date.now();
    const resp = http.post(`${BASE_URL}/api/v1/watchlist`,
      JSON.stringify({ cryptocurrency_id: coinId }),
      { headers }
    );
    watchlistAddLatency.add(Date.now() - start);

    // 201 = added, 409 = already exists (both valid under concurrent load)
    const ok = check(resp, {
      "add watchlist ok": (r) => [201, 409].includes(r.status),
    });
    addSuccessRate.add(ok);
  });

  group("remove from watchlist", () => {
    const start = Date.now();
    const resp = http.del(
      `${BASE_URL}/api/v1/watchlist/${coinId}`,
      null,
      { headers }
    );
    watchlistDelLatency.add(Date.now() - start);

    // 204 = deleted, 404 = wasn't there (both valid)
    check(resp, {
      "delete watchlist ok": (r) => [204, 404].includes(r.status),
    });
  });

  sleep(0.2);
}

export function handleSummary(data) {
  return {
    "k6/results/watchlist-summary.json": JSON.stringify(data, null, 2),
    stdout: textSummary(data),
  };
}

function textSummary(data) {
  const m = data.metrics;
  const p99 = (key) => m[key]?.values?.["p(99)"]?.toFixed(1) ?? "N/A";
  return [
    "\n── Watchlist Endpoint Performance Summary ──────────────",
    `  GET  p99 : ${p99("watchlist_get_duration")}ms`,
    `  POST p99 : ${p99("watchlist_add_duration")}ms`,
    `  DEL  p99 : ${p99("watchlist_del_duration")}ms`,
    `  add success rate : ${((m.watchlist_add_success?.values.rate ?? 0) * 100).toFixed(1)}%`,
    `  total reqs : ${m.http_reqs?.values.count}`,
    `  req/s      : ${m.http_reqs?.values.rate?.toFixed(1)}`,
    "────────────────────────────────────────────────────────\n",
  ].join("\n");
}
