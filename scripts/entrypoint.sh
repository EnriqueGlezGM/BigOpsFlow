#!/usr/bin/env bash
set -euo pipefail

ELASTIC_URL="${ELASTIC_URL:-http://elastic:9200}"
KIBANA_URL="${KIBANA_URL:-http://kibana:5601}"

echo "⏳ Waiting for Elasticsearch at ${ELASTIC_URL} ..."
until curl -fsS "${ELASTIC_URL}" >/dev/null; do sleep 2; done

echo "⏳ Waiting for Kibana at ${KIBANA_URL} ..."
until curl -fsS "${KIBANA_URL}/api/status" >/dev/null; do sleep 2; done

if [ -x /scripts/init-elastic-kibana.sh ]; then
  echo "🚀 Running init-elastic-kibana.sh ..."
  /scripts/init-elastic-kibana.sh || echo "⚠️ init script returned non-zero, continuing"
fi

echo "🚀 Starting Flask API ..."
exec python MY_flask_api.py