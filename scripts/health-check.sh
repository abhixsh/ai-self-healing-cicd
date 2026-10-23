#!/usr/bin/env bash
# Usage: scripts/health-check.sh [url] [retries]
set -euo pipefail
URL="${1:-http://localhost:5000/health}"
RETRIES="${2:-10}"

for i in $(seq 1 "$RETRIES"); do
  if curl -fsS "$URL" >/dev/null 2>&1; then
    echo "Healthy: $URL (attempt $i)"
    exit 0
  fi
  echo "Waiting for $URL (attempt $i/$RETRIES)..."
  sleep 2
done
echo "Unhealthy: $URL" >&2
exit 1
