# -*- coding: utf-8 -*-
# Streaming Kafka -> Enriquecido -> Predicción -> Mongo + Kafka + Elasticsearch
from pyspark.sql import SparkSession
from pyspark.sql.types import StructType, StructField, StringType, TimestampType, DoubleType
from pyspark.sql.functions import (
    from_json,
    col,
    hour,
    date_format,
    dayofweek,
    when,
    current_timestamp,
    coalesce,
    lit,
    to_timestamp,
)
from pyspark.ml import PipelineModel
import os
import datetime
from pyspark import SparkContext

# Cierra sesiones previas si las hay
try:
    _active = SparkSession.getActiveSession()
    if _active is not None:
        _active.stop()
except Exception:
    pass

if SparkContext._active_spark_context:
    SparkContext._active_spark_context.stop()

# SparkSession apuntando al cluster
spark = (
    SparkSession.builder
    .appName("analysis")
    .master("spark://spark-master-svc:7077")
    .getOrCreate()
)
spark.sparkContext.setLogLevel("ERROR")
print("✅ SparkSession creada")

# -------------------------
# 1) Cargar modelo
# -------------------------
print("🔧 Cargando PipelineModel...")
base_path = "/models/gbt"
default_model = f"{base_path}/best_pipeline"
model_dir = os.getenv("MODEL_DIR", f"{base_path}/pipeline_model")
if not os.path.isdir(model_dir):
    alt_model = default_model
    if os.path.isdir(alt_model):
        print(f"ℹ️  MODEL_DIR no encontrado ({model_dir}), usando alternativo {alt_model}")
        model_dir = alt_model
    else:
        raise FileNotFoundError(
            f"Modelo no encontrado en {model_dir}. "
            f"Asegura que el job de training haya escrito el PipelineModel o crea un symlink hacia {alt_model}."
        )
model = PipelineModel.load(model_dir)
print("✅ Modelo cargado:", model_dir)

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "kafka:9092")
REQUEST_TOPIC = os.getenv("REQUEST_TOPIC", "mydata_prediction_request")
RESPONSE_TOPIC = os.getenv("RESPONSE_TOPIC", "mydata_prediction_response")
MONGO_URI = os.getenv("MONGO_URI", "mongodb://mongo:27017")
MONGO_DB = os.getenv("MONGO_DB", "agile_data_science")
MONGO_COLL = os.getenv("MONGO_COLL", "mydata_prediction_response")
ELASTIC_URL = os.getenv("ELASTIC_URL", "http://elastic:9200")
ELASTIC_INDEX = os.getenv("ELASTIC_INDEX", "mydata_prediction_response")

# -------------------------
# 2) Esquema de entrada (incluye UUID)
# -------------------------
schema = StructType([
    StructField("UUID", StringType(), True),
    StructField("customer_id", StringType(), True),
    StructField("restaurant_id", StringType(), True),
    StructField("order_date_and_time", TimestampType(), True),
    StructField("order_value", DoubleType(), True),
    StructField("delivery_fee", DoubleType(), True),
    StructField("payment_method", StringType(), True),
    StructField("discounts_and_offers", StringType(), True),
    StructField("commission_fee", DoubleType(), True),
    StructField("payment_processing_fee", DoubleType(), True),
    StructField("refunds/chargebacks", DoubleType(), True),
])

# --- Crear los topics de Kafka si no existen ---
from kafka.admin import KafkaAdminClient, NewTopic
from kafka.errors import TopicAlreadyExistsError

try:
    admin = KafkaAdminClient(bootstrap_servers=KAFKA_BOOTSTRAP, client_id="init-topics")
    topics = [
        NewTopic(name=REQUEST_TOPIC, num_partitions=1, replication_factor=1),
        NewTopic(name=RESPONSE_TOPIC, num_partitions=1, replication_factor=1),
    ]
    admin.create_topics(topics)
    print(f"✅ Topics de Kafka creados ({REQUEST_TOPIC}, {RESPONSE_TOPIC})")
    admin.close()
except TopicAlreadyExistsError:
    print("ℹ️  Los topics ya existían")
except Exception as e:
    print(f"⚠️  No se pudieron crear los topics automáticamente: {e}")

# -------------------------
# 3) Lectura desde Kafka
# -------------------------
print(f"🔌 Conectando a Kafka (topic: {REQUEST_TOPIC})...")
raw_stream = (
    spark.readStream
    .format("kafka")
    .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP)
    .option("subscribe", REQUEST_TOPIC)
    .option("startingOffsets", "latest")   # "earliest" para reconsumir
    .load()
)

json_df = (
    raw_stream
    .selectExpr("CAST(value AS STRING) AS json_data")
    .select(from_json("json_data", schema, {"timestampFormat": "yyyy-MM-dd'T'HH:mm:ss[XXX][XX][X]"}).alias("data"))
    .select("data.*")
    .withColumn("order_date_and_time", to_timestamp(col("order_date_and_time")))
)

# -------------------------
# 4) Enriquecimiento
# -------------------------
df_enriched = (
    json_df
    .withColumn("day_of_week_num", dayofweek("order_date_and_time"))
    .withColumn("day_of_week", date_format("order_date_and_time", "EEEE"))
    .withColumn("hour_of_day", hour("order_date_and_time"))
    .withColumn("hour_of_day_str", col("hour_of_day").cast("string"))
    .withColumn("es_fin_de_semana", when(col("day_of_week_num").isin([1, 7]), 1).otherwise(0))
    .withColumn("es_hora_punta", when(
        (col("hour_of_day").between(13, 15)) | (col("hour_of_day").between(20, 22)), 1
    ).otherwise(0))
    .withColumn("has_discount", when(col("discounts_and_offers").isNotNull(), 1).otherwise(0))
    .withColumn("discount_value", when(col("has_discount") == 1, col("order_value") * 0.1).otherwise(0.0))
    .withColumn("refunded", when(col("refunds/chargebacks") > 0, 1).otherwise(0))
    .withColumn("order_value_dbl", col("order_value").cast("double"))
    .withColumn("delivery_fee_dbl", col("delivery_fee").cast("double"))
    .withColumn("commission_fee_dbl", col("commission_fee").cast("double"))
    .withColumn("payment_processing_fee_dbl", col("payment_processing_fee").cast("double"))
    .withColumn("refunds_chargebacks_dbl", col("refunds/chargebacks").cast("double"))
)

# -------------------------
# 5) Selección de columnas (modelo + contexto)
# -------------------------
required_numeric = [
    "order_value_dbl", "delivery_fee_dbl", "commission_fee_dbl", "payment_processing_fee_dbl",
    "refunds_chargebacks_dbl", "discount_value", "has_discount", "refunded",
    "es_fin_de_semana", "es_hora_punta"
]
required_categorical = ["day_of_week", "hour_of_day_str", "payment_method", "discounts_and_offers"]
feature_cols = list(dict.fromkeys(required_numeric + required_categorical))
context_cols = {
    "payment_method": "payment_method_ctx",
    "discounts_and_offers": "discounts_and_offers_ctx",
    "order_date_and_time": "order_date_and_time_ctx",
}
DEFAULT_NULL_FILL = {
    "day_of_week": "unknown",
    "hour_of_day_str": "0",
    "payment_method": "unknown",
    "discounts_and_offers": "none",
}

dedup_enriched = (
    df_enriched
    .withWatermark("order_date_and_time", "1 hour")
    .dropDuplicates(["UUID"])
)


def log_sample(df, label, columns):
    """Log small, safe samples to debug microbatch content."""
    try:
        sample = df.select(*columns).limit(3).toJSON().collect()
        if sample:
            print(f"🔎 {label}: {sample}")
    except Exception as e:
        print(f"⚠️  No se pudo obtener muestra {label}: {e}")

def ensure_es_index(es_url, index_name):
    import urllib.request, urllib.error, json

    mappings_body = {
        "settings": {"number_of_shards": 1, "number_of_replicas": 0},
        "mappings": {
            "properties": {
                "@timestamp": {
                    "type": "date",
                    "format": "strict_date_optional_time||epoch_millis",
                }
            }
        },
    }

    try:
        head_req = urllib.request.Request(f"{es_url.rstrip('/')}/{index_name}", method="HEAD")
        with urllib.request.urlopen(head_req, timeout=5):
            return True
    except urllib.error.HTTPError as he:
        if he.code == 404:
            print(f"ℹ️  Índice ES {index_name} no existe, intentando crearlo...")
            body = json.dumps(mappings_body)
            try:
                put_req = urllib.request.Request(
                    f"{es_url.rstrip('/')}/{index_name}",
                    data=body.encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="PUT",
                )
                with urllib.request.urlopen(put_req, timeout=10):
                    print(f"✅ Índice ES {index_name} creado")
                    return True
            except Exception as e:
                print(f"⚠️  No se pudo crear el índice {index_name}: {e}")
        else:
            print(f"⚠️  Error comprobando índice {index_name}: {he}")
    except Exception as e:
        print(f"⚠️  Error comprobando índice {index_name}: {e}")
    return False


# -------------------------
# 7) foreachBatch: Mongo + Kafka + Elasticsearch (Bulk)
# -------------------------
def write_to_mongo_kafka_es(batch_df, epoch_id):
    import pymongo, json, urllib.request, urllib.error
    from uuid import uuid4

    client = None
    try:
        rows = [r.asDict() for r in batch_df.collect()]
        print(f"🧱 Microbatch {epoch_id}: {len(rows)} docs para sinks")
        if not rows:
            return

        # Copia para ES
        es_rows = []
        for d in rows:
            d_es = dict(d)
            d_es.pop("_id", None)
            # Normaliza timestamps a ISO para que casen con mapping date
            for k, v in list(d_es.items()):
                if isinstance(v, datetime.datetime):
                    try:
                        d_es[k] = v.isoformat()
                    except Exception:
                        pass
            es_rows.append(d_es)

        ensure_es_index(ELASTIC_URL, ELASTIC_INDEX)

        # Bulk ES
        ndjson_lines = []
        for d in es_rows:
            es_id = d.get("UUID") or str(uuid4())
            ndjson_lines.append(json.dumps({"index": {"_index": ELASTIC_INDEX, "_id": es_id}}))
            ndjson_lines.append(json.dumps(d, default=str))
        payload = ("\n".join(ndjson_lines) + "\n").encode("utf-8")

        try:
            req = urllib.request.Request(
                f"{ELASTIC_URL.rstrip('/')}/_bulk", data=payload,
                headers={"Content-Type": "application/x-ndjson"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                body = resp.read().decode("utf-8", errors="replace")
            es_resp = json.loads(body)
            if es_resp.get("errors", False):
                print("❌ ES bulk con errores:", body[:800], "...")
        except urllib.error.HTTPError as he:
            body = he.read().decode("utf-8", errors="replace")
            print(f"❌ ES HTTPError {he.code}: {body[:800]}")
        except Exception as e:
            print("❌ Error conectando a ES:", e)

        # Kafka respuesta
        (batch_df
         .selectExpr("UUID as key", "to_json(struct(*)) as value")
         .write
         .format("kafka")
         .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP)
         .option("topic", RESPONSE_TOPIC)
         .save())

        # Mongo
        client = pymongo.MongoClient(MONGO_URI)
        db = client[MONGO_DB]
        out = db[MONGO_COLL]
        out.create_index([("UUID", pymongo.ASCENDING)], name="idx_uuid", unique=False, background=True)
        out.create_index([("@timestamp", pymongo.DESCENDING)], name="idx_timestamp", background=True)
        rows_for_mongo = [dict(d) for d in es_rows]
        out.insert_many(rows_for_mongo)

    except Exception as e:
        print("❌ Error en foreachBatch:", e)
        try:
            if client is None:
                client = pymongo.MongoClient(MONGO_URI)
            db = client[MONGO_DB]
            db["mydata_prediction_errors"].insert_one({
                "epoch_id": int(epoch_id),
                "error": str(e),
                "note": "Fallo en foreachBatch",
            })
        except Exception as e2:
            print("❌ Error registrando error en Mongo:", e2)
    finally:
        try:
            client and client.close()
        except Exception:
            pass

# -------------------------
# 8) Lanzar el stream
# -------------------------
def process_batch(batch_df, epoch_id):
    preds_batch = None
    try:
        pre_count = batch_df.count()
        print(f"🧱 Microbatch {epoch_id}: {pre_count} filas antes de transform")
        if pre_count == 0:
            return

        log_sample(
            batch_df,
            f"pre-transform {epoch_id}",
            ["UUID", "order_date_and_time", "payment_method", "discounts_and_offers"],
        )

        cleaned_batch = (
            batch_df
            .withColumn("payment_method", coalesce(col("payment_method"), lit(DEFAULT_NULL_FILL["payment_method"])))
            .withColumn("discounts_and_offers", coalesce(col("discounts_and_offers"), lit(DEFAULT_NULL_FILL["discounts_and_offers"])))
            .withColumn("day_of_week", coalesce(col("day_of_week"), lit(DEFAULT_NULL_FILL["day_of_week"])))
            .withColumn("hour_of_day_str", coalesce(col("hour_of_day_str"), lit(DEFAULT_NULL_FILL["hour_of_day_str"])))
            .withColumn("order_date_and_time", to_timestamp(col("order_date_and_time")))
            .withColumn("order_value_dbl", coalesce(col("order_value_dbl"), lit(0.0)))
            .withColumn("delivery_fee_dbl", coalesce(col("delivery_fee_dbl"), lit(0.0)))
            .withColumn("commission_fee_dbl", coalesce(col("commission_fee_dbl"), lit(0.0)))
            .withColumn("payment_processing_fee_dbl", coalesce(col("payment_processing_fee_dbl"), lit(0.0)))
            .withColumn("refunds_chargebacks_dbl", coalesce(col("refunds_chargebacks_dbl"), lit(0.0)))
        )

        features_batch = cleaned_batch.select("UUID", *[col(c) for c in feature_cols])
        preds_batch = model.transform(features_batch).cache()

        post_count = preds_batch.count()
        print(f"✅ Microbatch {epoch_id}: {post_count} filas tras transform")
        log_sample(preds_batch, f"post-transform {epoch_id}", ["UUID", "prediction"])

        context_batch = cleaned_batch.select(
            "UUID",
            col("payment_method").alias(context_cols["payment_method"]),
            col("discounts_and_offers").alias(context_cols["discounts_and_offers"]),
            col("order_date_and_time").alias(context_cols["order_date_and_time"]),
        )

        resultado_batch = (
            preds_batch
            .select("UUID", "prediction")
            .join(context_batch, on="UUID", how="left")
            .withColumn("@timestamp", current_timestamp())
        )

        write_to_mongo_kafka_es(resultado_batch, epoch_id)

    except Exception as e:
        print(f"❌ Error procesando microbatch {epoch_id}: {e}")
    finally:
        try:
            preds_batch is not None and preds_batch.unpersist()
        except Exception:
            pass


print("🚀 Iniciando streaming (Mongo + Kafka + Elasticsearch)...")
checkpoint_dir = os.getenv("CHECKPOINT_DIR", "/models/checkpoints/prediction-v1")
query = (
    dedup_enriched.writeStream
    .outputMode("append")
    .option("checkpointLocation", checkpoint_dir)  # persistente en PVC si existe
    .foreachBatch(process_batch)
    .start()
)
print("🏃 Stream RUNNING en puerto 4042 (UI). ⏳ Esperando microbatches...")
query.awaitTermination()
