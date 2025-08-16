# Food Delivery – Streaming Predictions (Kafka → Spark → Mongo/Elastic → Flask UI)

Pipeline de predicción en tiempo real con:
- **Kafka** (peticiones/respuestas),
- **Spark Structured Streaming** (feature engineering + modelo),
- **MongoDB** (trazabilidad),
- **Elasticsearch + Kibana** (búsqueda/observabilidad),
- **Flask** (formulario web de entrada y polling de resultados),
- **Jupyter/Notebook** (job de streaming sencillo de ejecutar).

---

## 🧱 Requisitos

- Docker y Docker Compose
- Puertos libres:
  - Jupyter/Agile: `8888` (si lo expones)
  - Flask: `5050`
  - Kafka: `9092`
  - Mongo Express: `8081`
  - Elasticsearch: `9200`
  - Kibana: `5601`
  - Spark Master UI: `8080`

---

## 📦 Servicios (resumen)

- **agile**: entorno con Spark + Jupyter (para el job de streaming/notebooks).
- **predict_api**: Flask con formulario y endpoints (`/mydata/predict` + polling).
- **kafka**: broker Kafka.
- **mongo** + **mongo-express**: almacenamiento y UI simple.
- **elastic** + **kibana**: búsqueda/visualización.
- **(opcional)** script de bootstrap para crear **pipeline**, **index template**, **índice base**, **data view** y **modo oscuro** en Kibana.

---

## 🚀 Arranque rápido

```bash
docker compose up -d --build
```

Espera ~30–60s a que todo quede “healthy”.

---

## ✅ Comprobaciones rápidas

- **Spark Master UI**: http://localhost:8080  
- **Mongo Express**: http://localhost:8081  
  - DB `agile_data_science`
  - Colecciones: `mydata_prediction_response`, `mydata_prediction_errors`
- **Kibana**: http://localhost:5601  
  - Data View: `mydata_prediction_response*`
  - Campo temporal: `@ingest_ts`
- **Flask UI**: http://localhost:5050  

---

## 📡 Tópicos de Kafka

- **Entrada**: `mydata_prediction_request`
- **Salida**: `mydata_prediction_response`

---

## 🔮 Modelo

El modelo se carga desde `./models/pipeline_model.bin` (dentro de **agile**).  
Asegúrate de que el path existe en el contenedor.

---

## 🧪 Probar de extremo a extremo

### 1) Lanza el job de streaming (Notebook)

```bash
docker exec -it agile bash
```

Luego abre Jupyter y ejecuta **Run All** en el notebook `MY_Make predictions.ipynb`  
o bien usa el script `.py` equivalente.

El job debe mostrar logs tipo:

```
🔧 Creando SparkSession...
✅ SparkSession creada
🔧 Cargando PipelineModel...
✅ Modelo cargado
🔌 Conectando a Kafka (topic: mydata_prediction_request)...
🚀 Iniciando streaming (Mongo + Kafka + Elasticsearch)...
⏳ Esperando microbatches...
```

### 2) Abre la UI Flask

http://localhost:5050  
- Rellena el formulario y envíalo.  
- Se devuelve un `UUID` y empieza el **polling**.  
- Cuando Spark produce la predicción, aparece en pantalla y se guarda en **Mongo**, **Kafka** y **Elasticsearch**.

### 3) Revisa en Kibana

- Abre **Discover**, Data View `mydata_prediction_response*`.
- Ajusta el rango de fechas → “Now”.
- Verás documentos con `UUID`, `order_id`, `prediction`, `@ingest_ts`, etc.

---

## 🧰 Endpoints útiles (Flask)

- `POST /mydata/predict` → envía un pedido, retorna `{"id": "...", "status": "submitted"}`  
- `GET /mydata/predict/response/<UUID>` → polling hasta tener predicción

---

## 🧪 Ejemplo de payload

```json
{
  "UUID": "generado-por-el-frontend",
  "order_id": 1,
  "customer_id": "cust_123",
  "restaurant_id": "rest_456",
  "order_date_and_time": "2025-08-06T13:00:00",
  "delivery_date_and_time": "2025-08-06T13:45:00",
  "order_value": 1000,
  "delivery_fee": 100,
  "payment_method": "credit_card",
  "discounts_and_offers": "10% off",
  "commission_fee": 100,
  "payment_processing_fee": 20,
  "refunds/chargebacks": 0
}
```

---

## 🧩 Bootstrap de Elasticsearch/Kibana (automático)

- Ingest Pipeline (quita `_id`, añade `@ingest_ts`, normaliza campos).
- Index Template e índice base `mydata_prediction_response`.
- Data View en Kibana (`mydata_prediction_response*`).
- Ajustes avanzados (modo oscuro, etc.).

---

## 🧹 Parar y limpiar

```bash
docker compose down
docker compose down -v   # ⚠️ borra volúmenes (Mongo/Elastic/Kibana)
```

---

## 🩺 Troubleshooting rápido

- **No aparecen jobs en Spark UI** → revisa SparkSession en el notebook.
- **No hay datos en Kibana** → revisa Mongo (`mydata_prediction_response`), amplía rango de fechas, verifica logs.
- **Errores en Elasticsearch** → pueden deberse a formatos de fecha; revisa logs del streaming.
- **Kafka vacío** → confirma que el formulario hace POST y que el job está leyendo `mydata_prediction_request`.

---

## 🏗️ Estructura del repo

```
.
├── docker-compose.yml
├── Dockerfile.predict_api
├── scripts/
│   └── init-elastic-kibana.sh
├── Food_delivery/
│   └── Deploying_Predictive_Systems/
│       ├── MY_Make predictions.ipynb
│       ├── web/
│       │   ├── MY_flask_api.py
│       │   └── my_form.html
│       └── models/
│           └── pipeline_model.bin
└── README.md
```

---

## 🧭 ¿Por qué usar notebook en vez de spark-submit?

- **Transparencia**: cada paso es visible y reproducible.  
- **Iteración rápida**: cambiar lógica sin recompilar ni reiniciar contenedores.  
- **Paridad**: el código del notebook es 1:1 con la versión `.py`.  
- **Simplicidad**: para demo/PoC, menos fricción.