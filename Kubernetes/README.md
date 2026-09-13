# BigOpsFlow en Kubernetes

[![Python](https://img.shields.io/badge/Python-3.13-blue?style=flat-square&logo=python&logoColor=white)](https://python.org/) [![Spark](https://img.shields.io/badge/Spark-4.0.1-orange?style=flat-square&logo=apachespark&logoColor=white)](https://spark.apache.org/) [![MongoDB](https://img.shields.io/badge/MongoDB-5.0.3-green?style=flat-square&logo=mongodb&logoColor=white)](https://mongodb.com/) [![Elasticsearch](https://img.shields.io/badge/Elasticsearch-9.1.2-yellow?style=flat-square&logo=elasticsearch&logoColor=black)](https://elastic.co/) [![Kafka](https://img.shields.io/badge/Kafka-3.7.1-black?style=flat-square&logo=apachekafka&logoColor=white)](https://kafka.apache.org/)

Despliegue local en Kubernetes del modelo de tiempo de entrega. Conserva el flujo distribuido existente: un Job entrena con Spark, un proceso de Structured Streaming consume solicitudes de Kafka y publica las predicciones en Kafka, MongoDB y Elasticsearch. La FastAPI solo valida y transporta las peticiones; no ejecuta el modelo.

## Datos y artefactos

El dataset se comparte fuera de `Compose` y `Kubernetes`:

```text
BigOpsFlow/
├── data/food_delivery/train.csv
├── Compose/
└── Kubernetes/
```

El Job busca `../data/food_delivery/train.csv`. Si no existe, lo descarga temporalmente en `/tmp` desde `gauravmalik26/food-delivery-dataset` con `kagglehub` y copia únicamente `train.csv` a esa ruta compartida. El PV tiene política `Retain` y `delete-stack.sh` no borra este dataset.

El entrenamiento escribe:

- modelo: `/models/food_delivery/pipeline_model`
- metadatos y métricas: `/models/food_delivery/model_metadata.json`
- checkpoint de streaming: `/models/checkpoints/prediction-v2`

## Despliegue

Requiere Docker Desktop con Kubernetes activo, `kubectl` y `envsubst`:

```bash
cd Kubernetes
./apply-stack.sh
```

El script realiza el flujo completo:

1. crea las carpetas persistentes;
2. construye `spark:4.0.1-py` con las dependencias del modelo;
3. aplica los manifiestos y crea los topics de Kafka;
4. recrea y espera a que termine `spark-submit-train`;
5. arranca la predicción en streaming con el modelo recién entrenado.

Para omitir la construcción cuando la imagen ya existe:

```bash
BUILD_SPARK_IMAGE=false ./apply-stack.sh
```

Seguimiento del entrenamiento y del streaming:

```bash
kubectl -n spark logs job/spark-submit-train -f
kubectl -n spark logs deployment/spark-stream-predict -c submit -f
kubectl -n spark get pods
```

## Probar una predicción

```bash
curl -X POST 'http://localhost:30550/predict-sync' \
  -H 'Content-Type: application/json' \
  -d '{
    "UUID": "test-k8s-1",
    "delivery_person_age": 29,
    "delivery_person_ratings": 4.7,
    "restaurant_latitude": 12.9716,
    "restaurant_longitude": 77.5946,
    "delivery_location_latitude": 13.0150,
    "delivery_location_longitude": 77.6200,
    "order_date_and_time": "2026-09-12T13:30:00Z",
    "weather_conditions": "Sunny",
    "road_traffic_density": "Medium",
    "vehicle_condition": 2,
    "type_of_order": "Meal",
    "type_of_vehicle": "motorcycle",
    "multiple_deliveries": 1,
    "festival": "No",
    "city": "Metropolitian"
  }'
```

`/predict-sync` crea primero el consumidor de respuestas, publica la solicitud y espera hasta 60 segundos. Devuelve HTTP 504 si el streaming no responde, en vez de mostrar una falsa predicción completada.

## Servicios locales

- FastAPI (`/healthz`, `/ready`, `/predict`, `/predict-sync`): `http://localhost:30550`
- Spark streaming UI: `http://localhost:30442`
- Elasticsearch: `http://localhost:30920`

- **[Formulario](http://localhost:30060)**
- **[Spark Master UI](http://localhost:30080)**
- **[Mongo Express](http://localhost:30881)**
- **[Kibana](http://localhost:30601)**


Los puertos son `NodePort`, por lo que no ocupan los puertos `5050` y `9200` usados por Compose.

## Limpieza del despliegue

```bash
./delete-stack.sh
```

El script elimina el namespace, los PV del despliegue y los artefactos locales de Kubernetes. Conserva `../data/food_delivery/train.csv` para que Compose y un futuro clúster reutilicen la misma fuente.
