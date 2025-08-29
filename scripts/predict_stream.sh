#!/usr/bin/env bash
set -euo pipefail

export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
export SPARK_HOME=/usr/local/spark
export PATH="$SPARK_HOME/bin:$PATH"
export PYSPARK_PYTHON=python
export PYSPARK_DRIVER_PYTHON=python
export PYSPARK_SUBMIT_ARGS="--packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.6 pyspark-shell"

# Asegura NumPy 1.x si la imagen trae 2.x
python - <<'PY'
import sys
try:
    import numpy as np
    ver = getattr(np, '__version__', '')
    if not ver.startswith('1.'):
        sys.exit(1)
except Exception:
    sys.exit(1)
sys.exit(0)
PY
if [ "$?" -ne 0 ]; then
  echo "⏬ Ajustando NumPy a <2 para compatibilidad..."
  python -m pip install --no-cache-dir 'numpy<2' >/dev/null 2>&1 || true
fi

PAPERMILL_BIN="/opt/conda/bin/papermill"
if [ ! -x "$PAPERMILL_BIN" ]; then PAPERMILL_BIN="papermill"; fi
"$PAPERMILL_BIN" \
  "/home/jovyan/Food_delivery/Deploying_Predictive_Systems/Make_Predictions.ipynb" \
  "/home/jovyan/Food_delivery/Deploying_Predictive_Systems/Make_Predictions.ipynb"
