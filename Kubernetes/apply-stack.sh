#!/usr/bin/env bash
set -euo pipefail

# Render k8s-spark.yaml substituyendo solo ${BASE_DIR} para no pisar
# variables como $POD_IP o $SPARK_LOCAL_IP dentro de los pods.
BASE_DIR="${BASE_DIR:-$(pwd)}"
export BASE_DIR

# Los PVs de Mongo y Elasticsearch usan hostPath bajo ${BASE_DIR}/data.
# delete-stack.sh borra esa carpeta y esta ignorada por git, asi que el
# despliegue debe recrearla antes de que kubelet intente montar los volumenes.
mkdir -p "${BASE_DIR}/data/mongo" "${BASE_DIR}/data/elastic"

# Asegura que el namespace exista antes de crear el ConfigMap
kubectl get namespace spark >/dev/null 2>&1 || kubectl create namespace spark

# Publica el HTML desde web/index.html como ConfigMap
kubectl -n spark create configmap predict-web \
  --from-file=index.html="${BASE_DIR}/web/index.html" \
  --dry-run=client -o yaml | kubectl apply -f -

envsubst '${BASE_DIR}' < k8s-spark.yaml | kubectl apply -f -
