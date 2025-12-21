#!/bin/bash

# Lanzar Spark master
$SPARK_HOME/sbin/start-master.sh


# Primer worker (puertos por defecto)
$SPARK_HOME/sbin/start-worker.sh spark://agile:7077

# Segundo worker (puertos distintos)
SPARK_WORKER_PORT=7078 \
SPARK_WORKER_WEBUI_PORT=8081 \
$SPARK_HOME/bin/spark-class org.apache.spark.deploy.worker.Worker spark://agile:7077 &

# Asegurar NumPy <2 en el entorno base de Python (Conda)
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
  echo "Ajustando NumPy a <2 en el arranque..."
  python -m pip install --no-cache-dir 'numpy<2' || true
fi

# Iniciar el microservicio Flask para lanzar Papermill (puerto 5000)
mkdir -p /home/jovyan/logs
PYBIN="/opt/conda/bin/python"
if [ ! -x "$PYBIN" ]; then PYBIN="python"; fi
"$PYBIN" /scripts/run_papermill.py \
  >/home/jovyan/logs/papermill_service.log 2>&1 &

# Orquestar automáticamente: entrenamiento -> predicción (en background)
# Controlado por ORCHESTRATE_ON_START (por defecto: true)
ORCHESTRATE_ON_START="${ORCHESTRATE_ON_START:-true}"
if [ "$ORCHESTRATE_ON_START" = "true" ] && [ -f /scripts/orchestrate_jobs.sh ]; then
  nohup bash /scripts/orchestrate_jobs.sh \
    >/home/jovyan/logs/orchestrator.log 2>&1 &
fi
