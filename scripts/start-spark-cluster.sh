#!/bin/bash

# Lanzar Spark master
$SPARK_HOME/sbin/start-master.sh


# Primer worker (puertos por defecto)
$SPARK_HOME/sbin/start-worker.sh spark://agile:7077

# Segundo worker (puertos distintos)
SPARK_WORKER_PORT=7078 \
SPARK_WORKER_WEBUI_PORT=8081 \
$SPARK_HOME/bin/spark-class org.apache.spark.deploy.worker.Worker spark://agile:7077 &

# # Inicia Jupyter (si quieres que lo vea el navegador)
# jupyter notebook --ip=0.0.0.0 --port=8888 --no-browser --allow-root || true