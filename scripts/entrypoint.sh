#!/usr/bin/env bash
# Container entrypoint. Migrations run before the app starts, and must be
# backward compatible with the version still serving traffic (expand/contract).
set -euo pipefail

if [[ "${RUN_MIGRATIONS:-true}" == "true" ]]; then
  echo "running migrations..."
  alembic upgrade head
fi

exec "$@"
