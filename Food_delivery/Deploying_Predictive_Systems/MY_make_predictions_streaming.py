#!/usr/bin/env python

#
# Run with: spark-submit --packages org.apache.spark:spark-sql-kafka-0-10_2.11:2.4.4 Food_delivery/Deploying_Predictive_Systems/MY_make_predictions_streaming.py $PROJECT_PATH
#
from pyspark.sql import SparkSession
from pyspark.sql.types import StructType, StructField, StringType, TimestampType, LongType
from pyspark.sql.functions import from_json, col, hour, dayofweek, when
from pyspark.ml import PipelineModel

print("✅ Script iniciado 1")

# Crear la SparkSession apuntando al cluster
spark = (
    SparkSession.builder
    .appName("PredictMyDataStreaming")
    .master("spark://agile:7077")
    .config("spark.driver.bindAddress", "0.0.0.0")
    .getOrCreate()
)

# spark = (
#     SparkSession.builder.config("spark.default.parallelism", 1)
#     .config(
#         "spark.jars.packages", "org.apache.spark:spark-sql-kafka-0-10_2.12:3.2.0"
#     )
#     .appName("PredictMyDataStreaming")
#     .getOrCreate()
# )


spark.sparkContext.setLogLevel("ERROR")

print("✅ Script iniciado 2")

# Cargar el modelo entrenado
modelo = PipelineModel.load("./models/pipeline_model.bin")

print("✅ Recibiendo mensaje de Kafka")

# Esquema del JSON recibido por Kafka
schema = StructType([
    StructField("order_id", LongType(), True),
    StructField("customer_id", StringType(), True),
    StructField("restaurant_id", StringType(), True),
    StructField("order_date_and_time", TimestampType(), True),
    StructField("delivery_date_and_time", TimestampType(), True),
    StructField("order_value", LongType(), True),
    StructField("delivery_fee", LongType(), True),
    StructField("payment_method", StringType(), True),
    StructField("discounts_and_offers", StringType(), True),
    StructField("commission_fee", LongType(), True),
    StructField("payment_processing_fee", LongType(), True),
    StructField("refunds/chargebacks", LongType(), True)
])

print("✅ Datos crudos de Kafka cargados")
# Leer desde Kafka
raw_stream = (
    spark.readStream
    .format("kafka")
    .option("kafka.bootstrap.servers", "kafka:9092")
    .option("subscribe", "mydata_prediction_request")
    .option("startingOffsets", "latest")
    .load()
)

# Decodificar el JSON
json_df = (
    raw_stream
    .selectExpr("CAST(value AS STRING) as json_data")
    .select(from_json("json_data", schema).alias("data"))
    .select("data.*")
)

# Añadir columnas derivadas como en el análisis
df_enriched = (
    json_df
    .withColumn("day_of_week", dayofweek("order_date_and_time"))
    .withColumn("hour_of_day", hour("order_date_and_time"))
    .withColumn("es_fin_de_semana", when(col("day_of_week").isin([1, 7]), 1).otherwise(0))
    .withColumn("es_hora_punta", when((col("hour_of_day").between(13, 15)) | (col("hour_of_day").between(20, 22)), 1).otherwise(0))
    .withColumn("has_discount", when(col("discounts_and_offers").isNotNull(), 1).otherwise(0))
    .withColumn("discount_value", when(col("has_discount") == 1, col("order_value") * 0.1).otherwise(0.0))
    .withColumn("refunded", when(col("refunds/chargebacks") > 0, 1).otherwise(0))
)

# Aplicar el modelo
predicciones = modelo.transform(df_enriched)

# Seleccionar solo lo relevante
resultado = predicciones.select("order_id", "prediction")

# Enviar resultados a Kafka
query = (
    resultado
    .selectExpr("CAST(order_id AS STRING) AS key", "to_json(struct(*)) AS value")
    .writeStream
    .format("kafka")
    .option("kafka.bootstrap.servers", "kafka:9092")
    .option("topic", "mydata_prediction_response")
    .option("checkpointLocation", "/tmp/kafka-checkpoints")
    .start()
)

query.awaitTermination()