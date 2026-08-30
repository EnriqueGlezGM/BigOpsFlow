#!/usr/bin/env bash

# Inicia el gateway Java antes de Jupyter/Papermill. Esto evita que un kernel
# multihilo tenga que hacer fork() bajo Rosetta (amd64 sobre host arm64).

gateway_dir="$(mktemp -d /tmp/pyspark-gateway.XXXXXX)"
gateway_info="${gateway_dir}/connection.info"
gateway_log="/home/jovyan/logs/pyspark_gateway.log"

export _PYSPARK_DRIVER_CONN_INFO_PATH="${gateway_info}"

# PythonGatewayServer termina al recibir EOF por stdin. Mantener abierta la
# tubería permite compartir el gateway con los kernels durante la vida del
# contenedor.
tail -f /dev/null | "${SPARK_HOME}/bin/spark-submit" \
  --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.6 \
  pyspark-shell \
  >"${gateway_log}" 2>&1 &
export PYSPARK_GATEWAY_PROCESS_PID=$!

gateway_tries=0
while [ ! -s "${gateway_info}" ] && [ "${gateway_tries}" -lt 60 ]; do
  sleep 1
  gateway_tries=$((gateway_tries + 1))
done

if [ ! -s "${gateway_info}" ]; then
  echo "ERROR: PySpark gateway did not create ${gateway_info}" >&2
  tail -50 "${gateway_log}" >&2 || true
  return 1
fi

gateway_values=$(python -c '
from pyspark.serializers import UTF8Deserializer, read_int
import sys
with open(sys.argv[1], "rb") as stream:
    print(read_int(stream))
    print(UTF8Deserializer().loads(stream))
' "${gateway_info}")

export PYSPARK_GATEWAY_PORT="$(printf '%s\n' "${gateway_values}" | sed -n '1p')"
export PYSPARK_GATEWAY_SECRET="$(printf '%s\n' "${gateway_values}" | sed -n '2p')"

echo "PySpark gateway ready on port ${PYSPARK_GATEWAY_PORT}."
