#!/usr/bin/env python3
"""Streaming Kafka -> modelo -> Kafka, MongoDB y Elasticsearch."""

import datetime
import json
import math
import os
import urllib.error
import urllib.request
from uuid import uuid4

import pymongo
from pyspark.ml import PipelineModel
from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    abs as sql_abs,
    asin,
    col,
    cos,
    current_timestamp,
    dayofweek,
    from_json,
    hour,
    lit,
    radians,
    sin,
    sqrt,
    struct,
    to_json,
    to_timestamp,
)
from pyspark.sql.types import DoubleType, StringType, StructField, StructType


KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "kafka:9092")
REQUEST_TOPIC = os.getenv("REQUEST_TOPIC", "mydata_prediction_request")
RESPONSE_TOPIC = os.getenv("RESPONSE_TOPIC", "mydata_prediction_response")
MONGO_URI = os.getenv("MONGO_URI", "mongodb://mongo:27017")
MONGO_DB = os.getenv("MONGO_DB", "agile_data_science")
MONGO_COLL = os.getenv("MONGO_COLL", "mydata_prediction_response")
ELASTIC_URL = os.getenv("ELASTIC_URL", "http://elastic:9200").rstrip("/")
ELASTIC_INDEX = os.getenv("ELASTIC_INDEX", "mydata_prediction_response")
MODEL_DIR = os.getenv("MODEL_DIR", "/models/food_delivery/pipeline_model")
CHECKPOINT_DIR = os.getenv("CHECKPOINT_DIR", "/models/checkpoints/prediction-v2")


SCHEMA = StructType(
    [
        StructField("UUID", StringType(), False),
        StructField("delivery_person_age", DoubleType(), True),
        StructField("delivery_person_ratings", DoubleType(), True),
        StructField("restaurant_latitude", DoubleType(), True),
        StructField("restaurant_longitude", DoubleType(), True),
        StructField("delivery_location_latitude", DoubleType(), True),
        StructField("delivery_location_longitude", DoubleType(), True),
        StructField("order_date_and_time", StringType(), True),
        StructField("weather_conditions", StringType(), True),
        StructField("road_traffic_density", StringType(), True),
        StructField("vehicle_condition", DoubleType(), True),
        StructField("type_of_order", StringType(), True),
        StructField("type_of_vehicle", StringType(), True),
        StructField("multiple_deliveries", DoubleType(), True),
        StructField("festival", StringType(), True),
        StructField("city", StringType(), True),
    ]
)


INDEX_MAPPING = {
    "properties": {
        "@ingest_ts": {"type": "date"},
        "UUID": {"type": "keyword"},
        "prediction": {"type": "double"},
        "order_date_and_time": {"type": "date"},
        "distance_km": {"type": "double"},
        "delivery_person_age": {"type": "double"},
        "delivery_person_ratings": {"type": "double"},
        "road_traffic_density": {"type": "keyword"},
        "weather_conditions": {"type": "keyword"},
        "vehicle_condition": {"type": "double"},
        "type_of_order": {"type": "keyword"},
        "type_of_vehicle": {"type": "keyword"},
        "multiple_deliveries": {"type": "double"},
        "festival": {"type": "keyword"},
        "city": {"type": "keyword"},
        "epoch_id": {"type": "long"},
    }
}


def ensure_elasticsearch_index() -> None:
    body = json.dumps({"mappings": INDEX_MAPPING}).encode("utf-8")
    try:
        req = urllib.request.Request(f"{ELASTIC_URL}/{ELASTIC_INDEX}", data=body, method="PUT")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=10):
            print(f"[ES] Índice {ELASTIC_INDEX} creado")
            return
    except urllib.error.HTTPError as exc:
        if exc.code != 400:
            raise

    req = urllib.request.Request(
        f"{ELASTIC_URL}/{ELASTIC_INDEX}/_mapping",
        data=json.dumps(INDEX_MAPPING).encode("utf-8"),
        method="PUT",
    )
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=10):
        print(f"[ES] Mapping de {ELASTIC_INDEX} actualizado")


def serialize_documents(batch_df, epoch_id):
    documents = []
    for row in batch_df.collect():
        document = row.asDict(recursive=True)
        for key, value in list(document.items()):
            if isinstance(value, (datetime.datetime, datetime.date)):
                document[key] = value.isoformat()
        document["prediction"] = float(document["prediction"])
        document["distance_km"] = float(document["distance_km"])
        document["epoch_id"] = int(epoch_id)
        documents.append(document)
    return documents


def write_outputs(batch_df, epoch_id) -> None:
    documents = serialize_documents(batch_df, epoch_id)
    if not documents:
        return

    response_rows = [
        {
            "UUID": document["UUID"],
            "prediction": document["prediction"],
            "distance_km": document["distance_km"],
        }
        for document in documents
    ]
    response_df = batch_df.sparkSession.createDataFrame(response_rows)
    (
        response_df.withColumn("key", col("UUID").cast("string"))
        .withColumn("value", to_json(struct("UUID", "prediction", "distance_km")))
        .selectExpr("CAST(key AS STRING)", "CAST(value AS STRING)")
        .write.format("kafka")
        .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP)
        .option("topic", RESPONSE_TOPIC)
        .save()
    )

    mongo_client = pymongo.MongoClient(MONGO_URI)
    try:
        collection = mongo_client[MONGO_DB][MONGO_COLL]
        # Compatible con el indice no unico creado por el flujo anterior.
        # El replace con upsert ya evita duplicar cada UUID.
        collection.create_index("UUID", unique=False, name="idx_uuid")
        for document in documents:
            collection.replace_one({"UUID": document["UUID"]}, document, upsert=True)
    finally:
        mongo_client.close()

    bulk_lines = []
    for document in documents:
        document_id = document.get("UUID") or str(uuid4())
        bulk_lines.append(json.dumps({"index": {"_index": ELASTIC_INDEX, "_id": document_id}}))
        bulk_lines.append(json.dumps(document))
    req = urllib.request.Request(
        f"{ELASTIC_URL}/_bulk?refresh=true",
        data=("\n".join(bulk_lines) + "\n").encode("utf-8"),
        method="POST",
    )
    req.add_header("Content-Type", "application/x-ndjson")
    with urllib.request.urlopen(req, timeout=30) as response:
        result = json.loads(response.read().decode("utf-8"))
    if result.get("errors"):
        raise RuntimeError("Elasticsearch devolvió errores durante la escritura bulk")
    print(f"[SINKS] Microbatch {epoch_id}: {len(documents)} predicciones persistidas")


def main() -> None:
    if not os.path.isdir(MODEL_DIR):
        raise FileNotFoundError(f"Modelo no encontrado en {MODEL_DIR}")

    spark = (
        SparkSession.builder.appName("Predict-Food-Delivery-Time-Streaming")
        .master("spark://spark-master-svc:7077")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")
    model = PipelineModel.load(MODEL_DIR)
    ensure_elasticsearch_index()

    raw_stream = (
        spark.readStream.format("kafka")
        .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP)
        .option("subscribe", REQUEST_TOPIC)
        .option("startingOffsets", "latest")
        .load()
    )
    parsed = (
        raw_stream.selectExpr("CAST(value AS STRING) AS json_data")
        .select(from_json("json_data", SCHEMA).alias("data"))
        .select("data.*")
        .withColumn("order_date_and_time", to_timestamp("order_date_and_time"))
    )
    normalized = (
        parsed.withColumn("restaurant_latitude", sql_abs("restaurant_latitude"))
        .withColumn("restaurant_longitude", sql_abs("restaurant_longitude"))
        .withColumn("delivery_location_latitude", sql_abs("delivery_location_latitude"))
        .withColumn("delivery_location_longitude", sql_abs("delivery_location_longitude"))
    )
    lat1 = radians(col("restaurant_latitude"))
    lon1 = radians(col("restaurant_longitude"))
    lat2 = radians(col("delivery_location_latitude"))
    lon2 = radians(col("delivery_location_longitude"))
    haversine_a = (
        sin((lat2 - lat1) / 2) * sin((lat2 - lat1) / 2)
        + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) * sin((lon2 - lon1) / 2)
    )
    enriched = (
        normalized.withColumn("distance_km", lit(2 * 6371.0) * asin(sqrt(haversine_a)))
        .withColumn("day_of_week", dayofweek("order_date_and_time").cast("double"))
        .withColumn("hour_sin", sin(lit(2 * math.pi) * hour("order_date_and_time") / lit(24.0)))
        .withColumn("hour_cos", cos(lit(2 * math.pi) * hour("order_date_and_time") / lit(24.0)))
        .withWatermark("order_date_and_time", "1 hour")
        .dropDuplicates(["UUID"])
    )

    output_columns = [
        "UUID",
        "prediction",
        "order_date_and_time",
        "distance_km",
        "delivery_person_age",
        "delivery_person_ratings",
        "road_traffic_density",
        "weather_conditions",
        "vehicle_condition",
        "type_of_order",
        "type_of_vehicle",
        "multiple_deliveries",
        "festival",
        "city",
    ]

    def process_batch(batch_df, epoch_id):
        if batch_df.rdd.isEmpty():
            return
        predictions = model.transform(batch_df).select(*output_columns).withColumn(
            "@ingest_ts", current_timestamp()
        )
        write_outputs(predictions, epoch_id)

    query = (
        enriched.writeStream.outputMode("append")
        .foreachBatch(process_batch)
        .option("checkpointLocation", CHECKPOINT_DIR)
        .start()
    )
    print(
        f"STREAMING_READY model=food-delivery-time-v2 topic={REQUEST_TOPIC} "
        f"checkpoint={CHECKPOINT_DIR}"
    )
    query.awaitTermination()


if __name__ == "__main__":
    main()
