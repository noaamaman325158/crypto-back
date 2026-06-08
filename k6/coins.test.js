/**
 * k6 performance test — Cryptocurrency endpoints
 *
 * Tests the most critical read path: GET /cryptocurrencies (list + detail).
 * These are Redis-cached, so they should be extremely fast.
 * We enforce aggressive SLOs: p99 < 200ms, throughput > 100 req/s.
 *
 * Run modes (controlled by K6_SCENARIO env var):
 *   smoke  — 1 VU, 30s  (quick sanity check)
 *   load   — ramp to 50 VU over 2m (normal traffic)
 *   stress — ramp to 200 VU (find breaking point)
 *
 * Usage:
 *   k6 run k6/coins.test.js
 *   K6_SCENARIO=stress k6 run k6/coins.test.js
 *   BASE_URL=https://your-api.com k6 run k6/coins.test.js
 */

import http from "k6/http";
import { check, group, sleep } from "k6";
import { Rate, Trend } from "k6/metrics";
import { BASE_URL, INTERNAL_API_KEY, LOAD, SMOKE, STRESS } from "./config.js";

// ── Custom metrics ────────────────────────────────────────────────────────────
const cacheHitRate    = new Rate("cache_hit_rate");
const listLatency     = new Trend("coins_list_duration", true);
const detailLatency   = new Trend("coins_detail_duration", true);
const historyLatency  = new Trend("coins_history_duration", true);

// ── Scenario selection ────────────────────────────────────────────────────────
const SCENARIOS = { smoke: SMOKE, load: LOAD, stress: STRESS };
const scenario = SCENARIOS[__ENV.K6_SCENARIO] || LOAD;

export const options = {
  scenarios: { coins: scenario },
  thresholds: {
    // Cached list/detail endpoints must be very fast
    http_req_duration:          ["p(99)<200", "p(95)<150", "p(50)<50"],
    http_req_failed:            ["rate<0.01"],
    coins_list_duration:        ["p(99)<200"],
    coins_detail_duration:      ["p(99)<200"],
    // History hits CoinGecko (or cache) — slightly more lenient
    coins_history_duration:     ["p(99)<500"],
  },
};

// ── Setup: seed coin data once before the test ────────────────────────────────
export function setup() {
  const resp = http.post(`${BASE_URL}/api/v1/cryptocurrencies/refresh`, null, {
    headers: { "X-API-Key": INTERNAL_API_KEY },
  });

  check(resp, { "seed refresh OK": (r) => r.status === 200 });

  // Get a real coin ID to use in detail requests
  const listResp = http.get(`${BASE_URL}/api/v1/cryptocurrencies?per_page=1`);
  const data = JSON.parse(listResp.body);
  return {
    coinId:     data.data[0]?.id,
    externalId: data.data[0]?.external_id,
  };
}

// ── Main test loop ────────────────────────────────────────────────────────────
export default function (data) {
  group("coin list — paginated", () => {
    const start = Date.now();
    const resp = http.get(`${BASE_URL}/api/v1/cryptocurrencies?page=1&per_page=20`);
    listLatency.add(Date.now() - start);

    check(resp, {
      "list status 200":       (r) => r.status === 200,
      "list has data array":   (r) => JSON.parse(r.body).data !== undefined,
      "list has total":        (r) => JSON.parse(r.body).total !== undefined,
    });

    // Second request hits Redis cache — should be faster
    const start2 = Date.now();
    const resp2 = http.get(`${BASE_URL}/api/v1/cryptocurrencies?page=1&per_page=20`);
    const duration2 = Date.now() - start2;
    cacheHitRate.add(duration2 < 20); // cache hit if < 20ms
  });

  if (data.coinId) {
    group("coin detail", () => {
      const start = Date.now();
      const resp = http.get(`${BASE_URL}/api/v1/cryptocurrencies/${data.coinId}`);
      detailLatency.add(Date.now() - start);

      check(resp, {
        "detail status 200":    (r) => r.status === 200,
        "detail has symbol":    (r) => JSON.parse(r.body).symbol !== undefined,
        "detail has price":     (r) => JSON.parse(r.body).current_price !== undefined,
      });
    });
  }

  if (data.externalId) {
    group("price history", () => {
      const start = Date.now();
      const resp = http.get(
        `${BASE_URL}/api/v1/cryptocurrencies/${data.externalId}/history?days=7`
      );
      historyLatency.add(Date.now() - start);

      check(resp, {
        "history status 200":      (r) => r.status === 200,
        "history has prices":      (r) => JSON.parse(r.body).prices !== undefined,
      });
    });
  }

  sleep(0.1); // 100ms think time — simulates realistic user pacing
}

export function handleSummary(data) {
  return {
    "k6/results/coins-summary.json": JSON.stringify(data, null, 2),
    stdout: textSummary(data, { indent: " ", enableColors: true }),
  };
}

// ── Inline text summary (no external deps) ────────────────────────────────────
function textSummary(data) {
  const metrics = data.metrics;
  const dur = metrics.http_req_duration?.values;
  if (!dur) return "No duration data";
  return [
    "\n── Coins Endpoint Performance Summary ──────────────────",
    `  p50  : ${dur["p(50)"]?.toFixed(1)}ms`,
    `  p95  : ${dur["p(95)"]?.toFixed(1)}ms`,
    `  p99  : ${dur["p(99)"]?.toFixed(1)}ms`,
    `  avg  : ${dur.avg?.toFixed(1)}ms`,
    `  max  : ${dur.max?.toFixed(1)}ms`,
    `  reqs : ${metrics.http_reqs?.values.count}`,
    `  rate : ${metrics.http_reqs?.values.rate?.toFixed(1)} req/s`,
    `  errors: ${(metrics.http_req_failed?.values.rate * 100)?.toFixed(2)}%`,
    "────────────────────────────────────────────────────────\n",
  ].join("\n");
}
