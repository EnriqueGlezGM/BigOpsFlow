[![Python](https://img.shields.io/badge/Python-3.13-blue?style=flat-square&logo=python&logoColor=white)](https://python.org/) [![Spark](https://img.shields.io/badge/Spark-4.0.1-orange?style=flat-square&logo=apachespark&logoColor=white)](https://spark.apache.org/) [![MongoDB](https://img.shields.io/badge/MongoDB-5.0.3-green?style=flat-square&logo=mongodb&logoColor=white)](https://mongodb.com/) [![Elasticsearch](https://img.shields.io/badge/Elasticsearch-9.1.2-yellow?style=flat-square&logo=elasticsearch&logoColor=black)](https://elastic.co/) [![Kibana](https://img.shields.io/badge/Kibana-9.1.2-pink?style=flat-square&logo=kibana&logoColor=black)](https://elastic.co/) [![Kafka](https://img.shields.io/badge/Kafka-3.7.1-black?style=flat-square&logo=apachekafka&logoColor=white)](https://kafka.apache.org/)
[![Kubernetes](https://img.shields.io/badge/Kubernetes-1.25+-blue?style=flat-square&logo=kubernetes&logoColor=white)](https://kubernetes.io/)

Ver `k8s-spark.yaml` para configuración de PersistentVolumes y namespace `spark`.

---

## Limpieza total

Si quieres borrar todo (namespace + PVs + datos locales):

```bash
./delete-stack.sh
```

Esto elimina el namespace `spark`, los PVs (`models-pv`, `mongo-pv`, `elastic-pv`) y limpia directorios locales:
`models/gbt`, `models/checkpoints`, `data`, `models/jars`, `models/.ivy2*`, `models/.pylibs`.

## Despliegue

```bash
# 0) (Opcional) Build de imagen Spark personalizada
docker build -t spark:4.0.1-py spark4-py

# 1) Despliega el stack
./apply-stack.sh
```

## Entrenamiento del modelo

El job `spark-submit-train` entrena el modelo y guarda en `/models/gbt/pipeline_model`:

```bash
kubectl -n spark logs job/spark-submit-train -f
```

## Arrancar el streaming

El streaming lee de Kafka, aplica el modelo y escribe a Kafka/Mongo/Elasticsearch.

```bash
kubectl -n spark rollout restart deploy/spark-stream-predict
kubectl -n spark logs deploy/spark-stream-predict -c check-model --follow
kubectl -n spark logs deploy/spark-stream-predict -c submit --follow
```

## Probar el ingest

Sin port-forward. El servicio `predict-ingest` expone un LoadBalancer en `localhost:5050`.

```bash
curl -X POST 'http://localhost:5050/predict-sync' \
  -H 'Content-Type: application/json' \
  -d '{
    "UUID":"test-10",
    "customer_id":"c1",
    "restaurant_id":"r1",
    "order_date_and_time":"2024-05-10T12:34:00Z",
    "order_value":25.5,
    "delivery_fee":3.0,
    "payment_method":"card",
    "discounts_and_offers":null,
    "commission_fee":2.0,
    "payment_processing_fee":0.5,
    "refunds/chargebacks":0.0
  }'
```

`/predict-sync` espera la respuesta y devuelve la prediccion.

## Web UI

La web esta en `http://localhost:30060` y muestra la prediccion en grande.
El boton se habilita cuando el job de streaming (analysis/predict) esta activo.

## Endpoints utiles

- Form web: `http://localhost:30060`
- API ingest (`/healthz`, `/ready`, `/predict-sync`): `http://localhost:5050`
- Spark streaming UI: `http://localhost:30442`
- Spark Master UI: `http://localhost:30080`
- Mongo Express: `http://localhost:30881`
- Kibana: `http://localhost:30601`
- Elasticsearch (ver puerto): `kubectl -n spark get svc elastic`
