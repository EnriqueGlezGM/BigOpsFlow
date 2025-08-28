#!/bin/bash

# Lanzar Spark master
$SPARK_HOME/sbin/start-master.sh


# Primer worker (puertos por defecto)
$SPARK_HOME/sbin/start-worker.sh spark://agile:7077

# Segundo worker (puertos distintos)
SPARK_WORKER_PORT=7078 \
SPARK_WORKER_WEBUI_PORT=8081 \
$SPARK_HOME/bin/spark-class org.apache.spark.deploy.worker.Worker spark://agile:7077 &

# Asegura NumPy <2 en el entorno base de Python (Conda)
python - <<'PY'
import sys
try:
    import numpy as np
    ver = getattr(np, '__version__', '')
    if not ver.startswith('1.'):
        raise SystemExit(1)
except Exception:
    raise SystemExit(1)
raise SystemExit(0)
PY
if [ "$?" -ne 0 ]; then
  echo "⏬ Ajustando NumPy a <2 en el arranque..."
  python -m pip install --no-cache-dir 'numpy<2' || true
fi

# Inicia el microservicio Flask para lanzar Papermill (puerto 5000)
python /scripts/run_papermill.py \
  >/home/jovyan/logs/papermill_service.log 2>&1 &

# # Inicia Jupyter (si quieres que lo vea el navegador)
# jupyter notebook --ip=0.0.0.0 --port=8888 --no-browser --allow-root || true
