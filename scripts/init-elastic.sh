#!/usr/bin/env bash
set -euo pipefail

# === Config ===
ES_URL="${ES_URL:-http://elastic:9200}"   # puedes sobreescribir con export ES_URL=...
PIPELINE_NAME="mydata_prediction_pipeline"
TEMPLATE_NAME="mydata_prediction_template"
INDEX_PATTERN="mydata_prediction_response*"

echo "🏁 Esperando a Elasticsearch en: $ES_URL ..."
# Espera a que / respondan sin error
until curl -sSf "$ES_URL" >/dev/null 2>&1; do
  echo "⏳ Elasticsearch aún no responde, reintentando en 2s..."
  sleep 2
done
echo "✅ Elasticsearch accesible."

echo "🔧 Creando/actualizando ingest pipeline: $PIPELINE_NAME"
curl -sS -X PUT "$ES_URL/_ingest/pipeline/$PIPELINE_NAME" \
  -H 'Content-Type: application/json' \
  -d @- <<'JSON'
{
  "processors": [
    { "remove":   { "field": "_id", "ignore_missing": true } },
    { "set":      { "field": "@ingest_ts", "value": "{{_ingest.timestamp}}", "override": false } },
    { "lowercase":{ "field": "payment_method", "ignore_missing": true } }
  ]
}
JSON
echo "✅ Pipeline listo."

echo "🧩 Creando/actualizando index template: $TEMPLATE_NAME"
curl -sS -X PUT "$ES_URL/_index_template/mydata_prediction_template" \
  -H 'Content-Type: application/json' \
  -d @- <<JSON
{
  "index_patterns": ["$INDEX_PATTERN"],
  "priority": 500,
  "template": {
    "settings": {
      "number_of_shards": 1,
      "number_of_replicas": 0,
      "index.default_pipeline": "$PIPELINE_NAME"
    },
    "mappings": {
      "date_detection": false,
      "dynamic": "false",
      "properties": {
        "UUID":                { "type": "keyword" },
        "order_id":            { "type": "long" },
        "prediction":          { "type": "double" },
        "order_date_and_time": { "type": "date", "format": "strict_date_optional_time||yyyy-MM-dd HH:mm:ss||epoch_millis" },
        "@ingest_ts":          { "type": "date", "format": "strict_date_optional_time||yyyy-MM-dd HH:mm:ss.SSSSSS||epoch_millis" },
        "payment_method":      { "type": "keyword" },
        "discounts_and_offers":{ "type": "keyword" },
        "day_of_week":         { "type": "integer" },
        "hour_of_day":         { "type": "integer" },
        "es_fin_de_semana":    { "type": "byte" },
        "es_hora_punta":       { "type": "byte" }
      }
    }
  }
}
JSON
echo "✅ Index template listo."

# (Opcional) Crear el índice base si no existe para que ya quede operativo
INDEX_NAME="mydata_prediction_response"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -I "$ES_URL/$INDEX_NAME")
if [ "$HTTP_CODE" = "404" ]; then
  echo "📁 Creando índice inicial: $INDEX_NAME"
  curl -sS -X PUT "$ES_URL/$INDEX_NAME" -H 'Content-Type: application/json' -d '{}'
  echo "✅ Índice creado."
else
  echo "ℹ️ Índice $INDEX_NAME ya existe (HTTP $HTTP_CODE)."
fi

echo "🎉 Elastic init completado."