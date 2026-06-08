#!/usr/bin/env bash
# Run all k6 performance tests locally.
# Prerequisites: k6 installed (brew install k6), server running on :8000
#
# Usage:
#   ./k6/run-all.sh                     # load test (default)
#   K6_SCENARIO=smoke ./k6/run-all.sh   # smoke test
#   K6_SCENARIO=stress ./k6/run-all.sh  # stress test
#   BASE_URL=https://your-api k6/run-all.sh
set -euo pipefail

SCENARIO=${K6_SCENARIO:-load}
BASE_URL=${BASE_URL:-http://localhost:8000}
RESULTS_DIR="k6/results"

mkdir -p "$RESULTS_DIR"

echo "▶ Running k6 performance tests"
echo "  Scenario : $SCENARIO"
echo "  Target   : $BASE_URL"
echo ""

run_test() {
  local name=$1
  local file=$2
  echo "── $name ────────────────────────────────────────────────"
  k6 run \
    --env K6_SCENARIO="$SCENARIO" \
    --env BASE_URL="$BASE_URL" \
    --env INTERNAL_API_KEY="${INTERNAL_API_KEY:-dev-internal-key}" \
    --out json="$RESULTS_DIR/${name}.json" \
    "$file"
  echo ""
}

run_test "coins"     k6/coins.test.js
run_test "auth"      k6/auth.test.js
run_test "watchlist" k6/watchlist.test.js

echo "✓ All tests complete. Results in $RESULTS_DIR/"
