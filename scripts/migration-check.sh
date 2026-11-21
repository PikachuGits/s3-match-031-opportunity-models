#!/usr/bin/env bash
# Prove the migration is reversible and the models match the DDL.
#
#   DATABASE_URL='postgresql+psycopg://USER:PASSWORD@127.0.0.1:5432/DB_NAME' \
#   ./scripts/migration-check.sh | tee evidence/migration-check.txt
set -euo pipefail
cd "$(dirname "$0")/.."

: "${DATABASE_URL:?DATABASE_URL is required}"

if [ -x .venv/bin/alembic ]; then
  ALEMBIC=.venv/bin/alembic
else
  ALEMBIC=alembic
fi

echo "== alembic current"
"$ALEMBIC" current

echo "== upgrade head"
"$ALEMBIC" upgrade head
"$ALEMBIC" current

echo "== downgrade base"
"$ALEMBIC" downgrade base
"$ALEMBIC" current

echo "== upgrade head (again)"
"$ALEMBIC" upgrade head
"$ALEMBIC" current

echo "== alembic check (models vs DDL)"
"$ALEMBIC" check
echo "OK: upgrade -> downgrade -> upgrade clean, no autogenerate drift"
