#!/usr/bin/env bash
# Run the full suite against the PostgreSQL 16 test database.
#
#   TEST_DATABASE_URL='postgresql+psycopg://USER:PASSWORD@127.0.0.1:5432/clawhunt_2056_test' \
#   EVIDENCE_OUT=evidence/test-results.txt ./scripts/test.sh
set -euo pipefail
cd "$(dirname "$0")/.."

: "${TEST_DATABASE_URL:?TEST_DATABASE_URL is required (database name must contain 'test')}"

if [ -x .venv/bin/python ]; then
  PY=.venv/bin/python
else
  PY=python3
fi

OUT="${EVIDENCE_OUT:-}"
if [ -n "$OUT" ]; then
  mkdir -p "$(dirname "$OUT")"
  "$PY" -m pytest -q "$@" 2>&1 | tee "$OUT"
  exit "${PIPESTATUS[0]}"
fi

exec "$PY" -m pytest -q "$@"
