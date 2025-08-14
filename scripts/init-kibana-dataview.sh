#!/usr/bin/env bash
set -euo pipefail

# =======================
# Config (sobrescribible por env)
# =======================
KIBANA_URL="${KIBANA_URL:-http://kibana:5601}"
SPACE_ID="${KIBANA_SPACE:-}"                         # ej: "default" o "observability" (vacío => espacio raíz)
DATA_VIEW_ID="${DATA_VIEW_ID:-mydata_prediction_response}"
DATA_VIEW_TITLE="${DATA_VIEW_TITLE:-mydata_prediction_response*}"
DATA_VIEW_NAME="${DATA_VIEW_NAME:-MyData Predictions}"
TIME_FIELD="${TIME_FIELD_NAME:-@ingest_ts}"

# Ruta base (si hay espacio, usa /s/<space_id>)
BASE_PATH="$KIBANA_URL"
if [[ -n "$SPACE_ID" ]]; then
  BASE_PATH="$KIBANA_URL/s/$SPACE_ID"
fi

echo "🏁 Esperando a Kibana en: $KIBANA_URL ..."
# Espera a que Kibana responda
until curl -sSf "$KIBANA_URL/api/status" >/dev/null 2>&1; do
  echo "⏳ Kibana aún no responde, reintentando en 2s..."
  sleep 2
done
echo "✅ Kibana accesible."

create_payload() {
  cat <<JSON
{
  "data_view": {
    "id": "${DATA_VIEW_ID}",
    "title": "${DATA_VIEW_TITLE}",
    "name": "${DATA_VIEW_NAME}",
    "timeFieldName": "${TIME_FIELD}"
  }
}
JSON
}

update_payload() {
  cat <<JSON
{
  "data_view": {
    "title": "${DATA_VIEW_TITLE}",
    "name": "${DATA_VIEW_NAME}",
    "timeFieldName": "${TIME_FIELD}"
  }
}
JSON
}

# =======================
# Crear o actualizar Data View
# =======================
echo "🔧 Creando Data View '${DATA_VIEW_NAME}' (id='${DATA_VIEW_ID}') para patrón '${DATA_VIEW_TITLE}'..."

CREATE_CODE=$(curl -s -o /tmp/dv_create.out -w "%{http_code}" \
  -X POST "${BASE_PATH}/api/data_views/data_view" \
  -H 'kbn-xsrf: true' \
  -H 'Content-Type: application/json' \
  -d "$(create_payload)" || true)

if [[ "$CREATE_CODE" == "409" ]]; then
  echo "ℹ️ Ya existe. Actualizando Data View '${DATA_VIEW_ID}'..."
  UPDATE_CODE=$(curl -s -o /tmp/dv_update.out -w "%{http_code}" \
    -X PUT "${BASE_PATH}/api/data_views/data_view/${DATA_VIEW_ID}" \
    -H 'kbn-xsrf: true' \
    -H 'Content-Type: application/json' \
    -d "$(update_payload)" || true)
  if [[ "$UPDATE_CODE" =~ ^2 ]]; then
    echo "✅ Data View actualizado."
  else
    echo "❌ Error actualizando (HTTP $UPDATE_CODE):"
    cat /tmp/dv_update.out; echo
    exit 1
  fi
elif [[ "$CREATE_CODE" =~ ^2 ]]; then
  echo "✅ Data View creado."
else
  echo "❌ Error creando (HTTP $CREATE_CODE):"
  cat /tmp/dv_create.out; echo
  exit 1
fi

# =======================
# (Opcional) Establecer como Data View por defecto
# =======================
if [[ "${SET_DEFAULT_DV:-true}" == "true" ]]; then
  echo "⭐ Marcando '${DATA_VIEW_ID}' como Data View por defecto del espacio..."
  DEF_CODE=$(curl -s -o /tmp/dv_default.out -w "%{http_code}" \
    -X POST "${BASE_PATH}/api/kibana/settings" \
    -H 'kbn-xsrf: true' \
    -H 'Content-Type: application/json' \
    -d "{\"changes\": {\"defaultIndex\": \"${DATA_VIEW_ID}\"}}" || true)
  if [[ "$DEF_CODE" =~ ^2 ]]; then
    echo "✅ Data View por defecto actualizado."
  else
    echo "⚠️ No se pudo establecer por defecto (HTTP $DEF_CODE):"
    cat /tmp/dv_default.out; echo
  fi
fi

echo "🎉 init-kibana-dataview completado."