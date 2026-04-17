[![Python](https://img.shields.io/badge/Python-3.10%20%2F%203.13-blue?style=flat-square&logo=python&logoColor=white)](https://python.org/) [![Spark](https://img.shields.io/badge/Spark-3.5.6%20%2F%204.0.1-orange?style=flat-square&logo=apachespark&logoColor=white)](https://spark.apache.org/) [![MongoDB](https://img.shields.io/badge/MongoDB-5.0.3-green?style=flat-square&logo=mongodb&logoColor=white)](https://mongodb.com/) [![Elasticsearch](https://img.shields.io/badge/Elasticsearch-9.1.2-yellow?style=flat-square&logo=elasticsearch&logoColor=black)](https://elastic.co/) [![Kibana](https://img.shields.io/badge/Kibana-9.1.2-pink?style=flat-square&logo=kibana&logoColor=black)](https://elastic.co/) [![Kafka](https://img.shields.io/badge/Kafka-3.6%20%2F%203.7.1-black?style=flat-square&logo=apachekafka&logoColor=white)](https://kafka.apache.org/)

# BigOpsFlow

Pipeline de prediccion en tiempo real para Food Delivery. Entrena un modelo en Spark y sirve resultados por streaming con trazabilidad en bases de datos y analitica.

## Flujo de datos


```mermaid
graph LR
    A[UI/API] --> B[Kafka Request]
    B --> C[Spark Streaming]
    C --> D[Kafka Response]
    D --> E[MongoDB]
    D --> F[Elasticsearch]
    E --> G[UI/Kibana]
    F --> G
```


Para detalles específicos de cada método de despliegue, ver `Compose/README.md` o `Kubernetes/README.md`.

## Opciones de despliegue
| | Docker Compose | Kubernetes |
| --- | --- | --- |
| Uso recomendado | Local, dev, demo | Cluster o entorno K8s |
| Entrada de prediccion | Flask UI en `http://localhost:5050` | Web UI en `http://localhost:30060` + API en `http://localhost:5050` |
| Entrenamiento | Notebooks via microservicio (Papermill) | Job `spark-submit-train` |
| Persistencia | Volumenes Docker | PV/PVC hostPath |
| Guia completa | `Compose/README.md` | `Kubernetes/README.md` |

## Inicio rapido
**Docker Compose**:
```bash
cd Compose
docker compose up -d --build
```
Detalles, puertos y checks en `Compose/README.md`.

**Kubernetes**:
```bash
cd Kubernetes
docker build -t spark:4.0.1-py spark4-py
./apply-stack.sh
```
Pasos de entrenamiento, streaming y endpoints en `Kubernetes/README.md`.

## Estructura del repo
- `Compose/` stack local con Docker Compose, notebooks y scripts
- `Kubernetes/` manifiestos y utilidades para K8s
