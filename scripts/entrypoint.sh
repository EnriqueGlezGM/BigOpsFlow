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

# Opcional: lanzar entrenamiento/streaming automáticamente vía microservicio en agile
AUTO_RUN_TRAIN="${AUTO_RUN_TRAIN:-true}"
AUTO_RUN_PREDICT="${AUTO_RUN_PREDICT:-true}"

echo "⏳ Waiting for agile service at http://agile:5000 ..."
until curl -fsS "http://agile:5000/healthz" >/dev/null; do sleep 2; done

if [ "$AUTO_RUN_TRAIN" = "true" ]; then
  echo "🚀 Triggering training job on agile ..."
  curl -fsS -X POST "http://agile:5000/run-train" || echo "⚠️ train trigger failed"
fi

if [ "$AUTO_RUN_PREDICT" = "true" ]; then
  echo "🚀 Triggering prediction (stream) job on agile ..."
  curl -fsS -X POST "http://agile:5000/run-predict" || echo "⚠️ predict trigger failed"
fi

echo "🚀 Starting Flask API ..."
exec python Flask_API.py
