#!/usr/bin/env python

#
# Run with: spark-submit --packages org.apache.spark:spark-sql-kafka-0-10_2.11:2.4.4 ch08/make_predictions_streaming.py $PROJECT_PATH
#

import sys, os, re
import json
import datetime, iso8601

from pyspark import SparkContext, SparkConf
from pyspark.sql import SparkSession, Row
import pyspark.sql.types as T
import pyspark.sql.functions as F

# Save to Mongo
import pymongo


APP_NAME = "make_predictions_streaming.py"

# Process data every 10 seconds
PERIOD = 10
BROKERS = "kafka:9092"
PREDICTION_TOPIC = "flight_delay_classification_request"
MONGO_COLLECTION = "flight_delay_classification_response"


def main(base_path):

    spark = (
        SparkSession.builder.config("spark.default.parallelism", 1)
        .config(
            "spark.jars.packages", "org.apache.spark:spark-sql-kafka-0-10_2.12:3.2.0"
        )
        .appName(APP_NAME)
        .getOrCreate()
    )

    #
    # Load all models to be used in making predictions
    #

    # Load the arrival delay bucketizer
    from pyspark.ml.feature import Bucketizer

    arrival_bucketizer_path = "{}/models/arrival_bucketizer_2.0.bin".format(base_path)
    arrival_bucketizer = Bucketizer.load(arrival_bucketizer_path)

    # Load all the string field vectorizer pipelines into a dict
    from pyspark.ml.feature import StringIndexerModel

    string_indexer_models = {}
    for column in ["Carrier", "Origin", "Dest", "Route"]:
        string_indexer_model_path = "{}/models/string_indexer_model_{}.bin".format(
            base_path, column
        )
        string_indexer_model = StringIndexerModel.load(string_indexer_model_path)
        string_indexer_models[column] = string_indexer_model

    # Load the numeric vector assembler
    from pyspark.ml.feature import VectorAssembler

    vector_assembler_path = "{}/models/numeric_vector_assembler.bin".format(base_path)
    vector_assembler = VectorAssembler.load(vector_assembler_path)

    # Load the classifier model
    from pyspark.ml.classification import (
        RandomForestClassifier,
        RandomForestClassificationModel,
    )

    random_forest_model_path = (
        "{}/models/spark_random_forest_classifier.flight_delays.5.0.bin".format(
            base_path
        )
    )
    rfc = RandomForestClassificationModel.load(random_forest_model_path)

    #
    # Messages look like:
    #

    # {
    #   "Carrier": "DL",
    #   "DayOfMonth": 25,
    #   "DayOfWeek": 4,
    #   "DayOfYear": 359,
    #   "DepDelay": 10.0,
    #   "Dest": "LAX",
    #   "Distance": 2475.0,
    #   "FlightDate": "2015-12-25",
    #   "FlightNum": null,
    #   "Origin": "JFK",
    #   "Timestamp": "2019-10-31T00:19:47.633280",
    #   "UUID": "af74b096-ecc7-4493-a79a-ebcdff699385"
    # }

    #
    # Process Prediction Requests from Kafka
    #
    message_df = (
        spark.readStream.format("kafka")
        .option("kafka.bootstrap.servers", BROKERS)
        .option("subscribe", PREDICTION_TOPIC)
        .option("startingOffsets", "earliest")
        .load()
    )

    # Create a DataFrame out of the one-hot encoded RDD
    schema = T.StructType(
        [
            T.StructField("Carrier", T.StringType()),
            T.StructField("DayOfMonth", T.IntegerType()),
            T.StructField("DayOfWeek", T.IntegerType()),
            T.StructField("DayOfYear", T.IntegerType()),
            T.StructField("DepDelay", T.FloatType()),
            T.StructField("Dest", T.StringType()),
            T.StructField("Distance", T.FloatType()),
            T.StructField("FlightDate", T.StringType()),
            T.StructField("FlightNum", T.StringType()),
            T.StructField("Origin", T.StringType()),
            T.StructField("Timestamp", T.TimestampType()),
            T.StructField("UUID", T.StringType()),
        ]
    )

    prediction_requests_df = message_df.select(
        F.from_json(F.col("value").cast("string"), schema).alias("data")
    ).select("data.*")

    #
    # Add a Route variable to replace FlightNum
    #
    prediction_requests_with_route = prediction_requests_df.withColumn(
        "Route",
        F.concat(
            prediction_requests_df.Origin, F.lit("-"), prediction_requests_df.Dest
        ),
    )

    # Vectorize string fields with the corresponding pipeline for that column
    # Turn category fields into categoric feature vectors, then drop intermediate fields
    for column in ["Carrier", "Origin", "Dest", "Route"]:
        string_indexer_model = string_indexer_models[column]
        prediction_requests_with_route = string_indexer_model.transform(
            prediction_requests_with_route
        )

    # Vectorize numeric columns: DepDelay, Distance and index columns
    final_vectorized_features = vector_assembler.transform(
        prediction_requests_with_route
    )

    # Drop the individual index columns
    index_columns = ["Carrier_index", "Origin_index", "Dest_index", "Route_index"]
    for column in index_columns:
        final_vectorized_features = final_vectorized_features.drop(column)

    # Make the prediction
    predictions = rfc.transform(final_vectorized_features)

    # Drop the features vector and prediction metadata to give the original fields
    predictions = predictions.drop("Features_vec")
    final_predictions = (
        predictions.drop("indices")
        .drop("values")
        .drop("rawPrediction")
        .drop("probability")
    )

    # Store the results to MongoDB
    class MongoWriter:
        def open(self, partition_id, epoch_id):
            print(f"Opened partition id: {partition_id}, epoch: {epoch_id}")

            self.mongo_client = pymongo.MongoClient("mongo")
            print(f"Opened MongoClient: {self.mongo_client}")

            return True

        def process(self, row):
            print(f"Processing row: {row}")

            as_dict = row.asDict()
            print(f"Inserting row.asDict(): {as_dict}")

            id = self.mongo_client.agile_data_science.flight_delay_classification_response.insert_one(
                as_dict
            )
            print(f"Inserted row, got ID: {id.inserted_id}")

            self.mongo_client.close()

            return True

        def close(self, error):
            print("Closed with error: %s" % str(error))

            return True

    query = final_predictions.writeStream.foreach(MongoWriter()).start()

    query.awaitTermination()


if __name__ == "__main__":
    main("/home/jovyan")
