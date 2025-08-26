# Food Delivery – Streaming Predictions

Pipeline de predicción en tiempo real con:
- **Kafka**: peticiones/respuestas
- **Spark Structured Streaming** (feature engineering + modelo)
- **MongoDB**: trazabilidad
- **Elasticsearch + Kibana**: búsqueda/análisis,
- **Flask**: formulario web de entrada y polling de resultados
- **Jupyter/Notebook**: job de streaming sencillo de ejecutar

---

## Requisitos

- Docker y Docker Compose
- Puertos libres:
  - Jupyter/Agile: `8888`
  - Flask: `5050`
  - Kafka: `9092`
  - Mongo Express: `8081`
  - Elasticsearch: `9200`
  - Kibana: `5601`
  - Spark Master UI: `8080`

---

## Servicios

- **agile**: entorno con Spark + Jupyter (para el job de streaming/notebooks).
- **predict_api**: Flask con formulario y endpoints (`/mydata/predict` + polling).
- **kafka**: broker Kafka.
- **mongo** + **mongo-express**: almacenamiento y UI simple.
- **elastic** + **kibana**: búsqueda/visualización.

---

## Arranque rápido

```bash
docker compose up -d
```

Espera ~30–60s a que todo quede “healthy”.



Para crear el modelo:
```bash
docker exec -it -u jovyan agile bash -lc '
export JAVA_HOME=/usr/lib/jvm/java-11-openjdk-amd64
export SPARK_HOME=/usr/local/spark-3.2.0-bin-hadoop3.2
export PYSPARK_PYTHON=python
export PYSPARK_DRIVER_PYTHON=python
export PYSPARK_SUBMIT_ARGS="--packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.2.0 pyspark-shell"

papermill "/home/jovyan/Food_delivery/Analysis.ipynb" "/home/jovyan/Food_delivery/Analysis.ipynb"
'
```

Para la utilización del modelo:
```bash
docker exec -it -u jovyan agile bash -lc '
export JAVA_HOME=/usr/lib/jvm/java-11-openjdk-amd64
export SPARK_HOME=/usr/local/spark-3.2.0-bin-hadoop3.2
export PYSPARK_PYTHON=python
export PYSPARK_DRIVER_PYTHON=python
export PYSPARK_SUBMIT_ARGS="--packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.2.0 pyspark-shell"

papermill "/home/jovyan/Food_delivery/Deploying_Predictive_Systems/Make_Predictions.ipynb" "/home/jovyan/Food_delivery/Deploying_Predictive_Systems/Make_Predictions.ipynb"
'
```

Ir a la [web](http://localhost:5050) para lanzar predicciones.

---

## Comprobaciones rápidas

- **[Spark Master UI](http://localhost:8080)**
- **[JupyterLab](http://127.0.0.1:8080)**
- **[Mongo Express](http://localhost:8081)**
  - DB: [agile_data_science](http://localhost:8081/db/agile_data_science)
  - Colecciones: [mydata_prediction_response](http://localhost:8081/db/agile_data_science/mydata_prediction_response), [mydata_prediction_errors](http://localhost:8081/db/agile_data_science/mydata_prediction_errors)
- **[Kibana](http://localhost:5601)**
  - Data View: [mydata_prediction_response](http://localhost:5601/app/discover)
  - Campo temporal: `@ingest_ts`
- **[Flask UI](http://localhost:5050)**

---

## Topics de Kafka

- **Entrada**: `mydata_prediction_request`
- **Salida**: `mydata_prediction_response`

---

## Modelo

El modelo se carga desde `./models/pipeline_model.bin` (dentro de **agile**). 

---

## 🧹 Parar y limpiar

- **Detener los contenedores:**
```console
docker compose down
```

- **Eliminar todos los contenedores:**
```console
docker rm -f $(docker ps -a -q)
```

- **Eliminar todos los volúmenes:**
```console
docker volume rm $(docker volume ls -q)
```

- **Eliminar todas las imágenes:**
```console
docker rmi $(docker images -aq)
```

## ¿Por qué usar notebook en vez de spark-submit?

- **Transparencia**: cada paso es visible y reproducible.  
- **Iteración rápida**: cambiar lógica sin recompilar ni reiniciar contenedores.  
- **Paridad**: el código del notebook es 1:1 con la versión `.py`.  
- **Simplicidad**: para demo/PoC, menos fricción.