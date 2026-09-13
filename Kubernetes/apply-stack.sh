#!/usr/bin/env bash
set -euo pipefail

# Render k8s-spark.yaml substituyendo solo ${BASE_DIR} para no pisar
# variables como $POD_IP o $SPARK_LOCAL_IP dentro de los pods.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
BASE_DIR="${BASE_DIR:-${SCRIPT_DIR}}"
SHARED_DATA_DIR="${SHARED_DATA_DIR:-$(cd "${BASE_DIR}/.." && pwd -P)/data}"
export BASE_DIR SHARED_DATA_DIR
BUILD_SPARK_IMAGE="${BUILD_SPARK_IMAGE:-true}"

# Los PVs de Mongo y Elasticsearch usan hostPath bajo ${BASE_DIR}/data.
# delete-stack.sh borra esa carpeta y esta ignorada por git, asi que el
# despliegue debe recrearla antes de que kubelet intente montar los volumenes.
mkdir -p \
  "${BASE_DIR}/data/mongo" \
  "${BASE_DIR}/data/elastic" \
  "${SHARED_DATA_DIR}/food_delivery"

if [ "${BUILD_SPARK_IMAGE}" = "true" ]; then
  docker build -t spark:4.0.1-py "${BASE_DIR}/spark4-py"
fi

# Asegura que el namespace exista antes de crear el ConfigMap
kubectl get namespace spark >/dev/null 2>&1 || kubectl create namespace spark

# Los Jobs tienen plantillas inmutables. Se recrean para aplicar los cambios de
# datos/modelo y volver a entrenar en cada despliegue solicitado.
kubectl -n spark delete job \
  models-fix-perms spark-submit-train kibana-create-dataview \
  --ignore-not-found --wait=true

# Publica el HTML desde web/index.html como ConfigMap
kubectl -n spark create configmap predict-web \
  --from-file=index.html="${BASE_DIR}/web/index.html" \
  --dry-run=client -o yaml | kubectl apply -f -

envsubst '${BASE_DIR} ${SHARED_DATA_DIR}' < "${BASE_DIR}/k8s-spark.yaml" | kubectl apply -f -

# La inferencia sólo se habilita cuando el entrenamiento de esta ejecución ha
# terminado. Así la interfaz no envía peticiones a un modelo anterior.
kubectl -n spark scale deployment/spark-stream-predict --replicas=0
kubectl -n spark wait --for=condition=complete job/spark-submit-train --timeout=30m
kubectl -n spark scale deployment/spark-stream-predict --replicas=1
kubectl -n spark rollout status deployment/spark-stream-predict --timeout=10m
