#!/usr/bin/env bash
set -euo pipefail

# =========================================================
# Config (sobrescribible por variables de entorno)
# =========================================================
ES_URL="${ES_URL:-http://elastic:9200}"
KIBANA_URL="${KIBANA_URL:-http://kibana:5601}"
KIBANA_SPACE="${KIBANA_SPACE:-}"                       # ej: "default" | "" (raíz)

SET_DEFAULT_DV="${SET_DEFAULT_DV:-true}"

PIPELINE_NAME="${PIPELINE_NAME:-mydata_prediction_pipeline}"
TEMPLATE_NAME="${TEMPLATE_NAME:-mydata_prediction_template}"
INDEX_PATTERN="${INDEX_PATTERN:-mydata_prediction_response*}"
BASE_INDEX="${BASE_INDEX:-mydata_prediction_response}"

DATA_VIEW_ID="${DATA_VIEW_ID:-mydata_prediction_response}"
DATA_VIEW_TITLE="${DATA_VIEW_TITLE:-mydata_prediction_response*}"
DATA_VIEW_NAME="${DATA_VIEW_NAME:-MyData Predictions}"
TIME_FIELD_NAME="${TIME_FIELD_NAME:-@ingest_ts}"

# Advanced settings Kibana (puedes ampliar la lista)
KIBANA_ADV_SETTINGS_JSON="${KIBANA_ADV_SETTINGS_JSON:-{\"theme:darkMode\":true}}"

CURL_OPTS=(-sS --max-time 10)

# =========================================================
# Helpers
# =========================================================
log() { echo -e "$*"; }
ok()  { echo -e "✅ $*"; }
warn(){ echo -e "⚠️  $*" >&2; }
err() { echo -e "❌ $*" >&2; }

wait_for_es() {
  log "🏁 Esperando a Elasticsearch en: $ES_URL ..."
  local tries=0
  until curl "${CURL_OPTS[@]}" "$ES_URL" >/dev/null 2>&1; do
    tries=$((tries+1))
    if (( tries > 120 )); then err "Timeout esperando Elasticsearch"; exit 1; fi
    echo "⏳ ES no responde aún, reintentando en 2s..."
    sleep 2
  done
  ok "Elasticsearch accesible."
}

wait_for_kibana() {
  log "🏁 Esperando a Kibana en: $KIBANA_URL ..."
  local tries=0
  until curl "${CURL_OPTS[@]}" "$KIBANA_URL/api/status" >/dev/null 2>&1; do
    tries=$((tries+1))
    if (( tries > 120 )); then err "Timeout esperando Kibana"; exit 1; fi
    echo "⏳ Kibana no responde aún, reintentando en 2s..."
    sleep 2
  done
  ok "Kibana accesible."
}

kibana_base_path() {
  if [[ -n "$KIBANA_SPACE" ]]; then
    echo "$KIBANA_URL/s/$KIBANA_SPACE"
  else
    echo "$KIBANA_URL"
  fi
}

# =========================================================
# Elasticsearch: pipeline + template + índice base
# =========================================================
ensure_ingest_pipeline() {
  log "🔧 Creando/actualizando ingest pipeline: $PIPELINE_NAME"
  local code
  code=$(curl "${CURL_OPTS[@]}" -o /tmp/pipeline.out -w "%{http_code}" \
    -X PUT "$ES_URL/_ingest/pipeline/$PIPELINE_NAME" \
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
  ) || true
  if [[ "$code" =~ ^2 ]]; then ok "Pipeline listo."; else err "Error pipeline (HTTP $code):"; cat /tmp/pipeline.out; echo; fi
}

ensure_index_template() {
  log "🧩 Creando/actualizando index template: $TEMPLATE_NAME"
  local code
  code=$(curl "${CURL_OPTS[@]}" -o /tmp/template.out -w "%{http_code}" \
    -X PUT "$ES_URL/_index_template/$TEMPLATE_NAME" \
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
  ) || true
  if [[ "$code" =~ ^2 ]]; then ok "Index template listo."; else err "Error template (HTTP $code):"; cat /tmp/template.out; echo; fi
}

ensure_base_index() {
  local code
  code=$(curl "${CURL_OPTS[@]}" -o /dev/null -w "%{http_code}" -I "$ES_URL/$BASE_INDEX" || true)
  if [[ "$code" == "404" ]]; then
    log "📁 Creando índice inicial: $BASE_INDEX"
    local c2
    c2=$(curl "${CURL_OPTS[@]}" -o /tmp/index.out -w "%{http_code}" \
      -X PUT "$ES_URL/$BASE_INDEX" \
      -H 'Content-Type: application/json' -d '{}' || true)
    if [[ "$c2" =~ ^2 ]]; then ok "Índice creado."; else warn "No se pudo crear índice (HTTP $c2):"; cat /tmp/index.out; echo; fi
  else
    ok "Índice $BASE_INDEX ya existe (HTTP $code)."
  fi
}

# =========================================================
# Kibana: Data View (crear/actualizar) + Advanced Settings
# =========================================================
dv_create_payload() {
  cat <<JSON
{
  "data_view": {
    "id": "${DATA_VIEW_ID}",
    "title": "${DATA_VIEW_TITLE}",
    "name": "${DATA_VIEW_NAME}",
    "timeFieldName": "${TIME_FIELD_NAME}"
  }
}
JSON
}

dv_update_payload() {
  cat <<JSON
{
  "data_view": {
    "title": "${DATA_VIEW_TITLE}",
    "name": "${DATA_VIEW_NAME}",
    "timeFieldName": "${TIME_FIELD_NAME}"
  }
}
JSON
}

ensure_kibana_dataview() {
  local BASE; BASE=$(kibana_base_path)

  log "🔎 Comprobando Data View '${DATA_VIEW_ID}' en Kibana..."
  local code
  code=$(curl "${CURL_OPTS[@]}" -o /tmp/dv_get.out -w "%{http_code}" \
    -X GET "${BASE}/api/data_views/data_view/${DATA_VIEW_ID}" \
    -H 'kbn-xsrf: true' || true)

  if [[ "$code" == "404" ]]; then
    log "🔧 Creando Data View '${DATA_VIEW_ID}'..."
    code=$(curl "${CURL_OPTS[@]}" -o /tmp/dv_create.out -w "%{http_code}" \
      -X POST "${BASE}/api/data_views/data_view" \
      -H 'kbn-xsrf: true' -H 'Content-Type: application/json' \
      -d "$(dv_create_payload)" || true)
    if [[ "$code" =~ ^2 ]]; then ok "Data View creado."; else err "Error creando DV (HTTP $code):"; cat /tmp/dv_create.out; echo; fi
  elif [[ "$code" =~ ^2 ]]; then
    log "ℹ️ Ya existe. Actualizando Data View '${DATA_VIEW_ID}'..."
    code=$(curl "${CURL_OPTS[@]}" -o /tmp/dv_update.out -w "%{http_code}" \
      -X PUT "${BASE}/api/data_views/data_view/${DATA_VIEW_ID}" \
      -H 'kbn-xsrf: true' -H 'Content-Type: application/json' \
      -d "$(dv_update_payload)" || true)
    if [[ "$code" =~ ^2 ]]; then ok "Data View actualizado."; else warn "No se pudo actualizar (HTTP $code):"; cat /tmp/dv_update.out; echo; fi
  else
    warn "GET DV devolvió HTTP $code:"
    cat /tmp/dv_get.out; echo
  fi

  if [[ "$SET_DEFAULT_DV" == "true" ]]; then
    log "⭐ Estableciendo Data View por defecto: ${DATA_VIEW_ID}"
    code=$(curl "${CURL_OPTS[@]}" -o /tmp/dv_default.out -w "%{http_code}" \
      -X POST "${BASE}/api/kibana/settings" \
      -H 'kbn-xsrf: true' -H 'Content-Type: application/json' \
      -d "{\"changes\": {\"defaultIndex\": \"${DATA_VIEW_ID}\"}}" || true)
    if [[ "$code" =~ ^2 ]]; then ok "Default Data View actualizado."; else warn "No se pudo fijar por defecto (HTTP $code):"; cat /tmp/dv_default.out; echo; fi
  fi
}

# =========================================================
# Run
# =========================================================
wait_for_es
ensure_ingest_pipeline
ensure_index_template
ensure_base_index

wait_for_kibana
ensure_kibana_dataview

ok "🎉 bootstrap-analytics completado."