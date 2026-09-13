#!/usr/bin/env python3
"""Entrena el modelo de tiempo de entrega usado por el despliegue Kubernetes."""

import argparse
import json
import os
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
from pandas.api.types import is_object_dtype, is_string_dtype
from pyspark.ml import Pipeline
from pyspark.ml.evaluation import RegressionEvaluator
from pyspark.ml.feature import Imputer, OneHotEncoder, StringIndexer, VectorAssembler
from pyspark.ml.regression import RandomForestRegressor
from pyspark.sql import SparkSession
from pyspark.sql.functions import lit


DATASET_SLUG = "gauravmalik26/food-delivery-dataset"
EXPECTED_ROWS = 45593
SEED = 42


def resolve_dataset(path: Path) -> Path:
    if path.is_file():
        return path

    os.environ.setdefault("KAGGLEHUB_CACHE", "/tmp/kagglehub")
    import kagglehub

    downloaded = Path(kagglehub.dataset_download(DATASET_SLUG)) / "train.csv"
    if not downloaded.is_file():
        raise FileNotFoundError(f"No se ha encontrado train.csv en {downloaded}")

    path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(downloaded, path)
    print(f"[DATA] Dataset descargado y guardado en {path}")
    return path


def prepare_data(path: Path) -> tuple[pd.DataFrame, pd.Timestamp]:
    frame = pd.read_csv(path, skipinitialspace=True)
    if len(frame) != EXPECTED_ROWS:
        raise RuntimeError(
            f"El dataset ha cambiado: se esperaban {EXPECTED_ROWS} filas y hay {len(frame)}"
        )

    for column in frame.columns:
        if not (is_object_dtype(frame[column].dtype) or is_string_dtype(frame[column].dtype)):
            continue
        frame[column] = (
            frame[column]
            .str.strip()
            .replace({"NaN": np.nan, "nan": np.nan, "conditions NaN": np.nan})
        )

    frame["delivery_time_min"] = pd.to_numeric(
        frame["Time_taken(min)"].str.extract(r"(\d+)", expand=False), errors="coerce"
    )
    frame["order_date"] = pd.to_datetime(frame["Order_Date"], dayfirst=True, errors="coerce")
    frame["hour_of_day"] = pd.to_numeric(
        frame["Time_Orderd"].str.extract(r"^(\d+)", expand=False), errors="coerce"
    ).mod(24)
    frame = frame.rename(
        columns={
            "Delivery_person_Age": "delivery_person_age",
            "Delivery_person_Ratings": "delivery_person_ratings",
            "Restaurant_latitude": "restaurant_latitude",
            "Restaurant_longitude": "restaurant_longitude",
            "Delivery_location_latitude": "delivery_location_latitude",
            "Delivery_location_longitude": "delivery_location_longitude",
            "Weatherconditions": "weather_conditions",
            "Road_traffic_density": "road_traffic_density",
            "Vehicle_condition": "vehicle_condition",
            "Type_of_order": "type_of_order",
            "Type_of_vehicle": "type_of_vehicle",
            "Festival": "festival",
            "City": "city",
        }
    )

    coordinates = [
        "restaurant_latitude",
        "restaurant_longitude",
        "delivery_location_latitude",
        "delivery_location_longitude",
    ]
    for column in coordinates:
        frame[column] = pd.to_numeric(frame[column], errors="coerce").abs()
    for column in [
        "delivery_person_age",
        "delivery_person_ratings",
        "vehicle_condition",
        "multiple_deliveries",
    ]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")

    frame = frame.loc[
        frame["delivery_time_min"].notna()
        & frame["order_date"].notna()
        & frame[coordinates].notna().all(axis=1)
        & frame[["restaurant_latitude", "restaurant_longitude"]].ne(0).all(axis=1)
    ].copy()

    lat1 = np.radians(frame["restaurant_latitude"])
    lon1 = np.radians(frame["restaurant_longitude"])
    lat2 = np.radians(frame["delivery_location_latitude"])
    lon2 = np.radians(frame["delivery_location_longitude"])
    haversine_a = (
        np.sin((lat2 - lat1) / 2) ** 2
        + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    )
    frame["distance_km"] = 2 * 6371.0 * np.arcsin(np.sqrt(haversine_a))
    frame["day_of_week"] = frame["order_date"].dt.dayofweek + 1
    frame["hour_sin"] = np.sin(2 * np.pi * frame["hour_of_day"] / 24)
    frame["hour_cos"] = np.cos(2 * np.pi * frame["hour_of_day"] / 24)
    frame["weather_conditions"] = frame["weather_conditions"].str.replace(
        r"^conditions\s+", "", regex=True
    )

    categorical_columns = [
        "weather_conditions",
        "road_traffic_density",
        "type_of_order",
        "type_of_vehicle",
        "festival",
        "city",
    ]
    for column in categorical_columns:
        frame[column] = frame[column].fillna("Unknown").astype(str).str.strip()

    temporal_cutoff = frame["order_date"].quantile(0.8)
    frame["dataset_split"] = np.where(
        frame["order_date"] <= temporal_cutoff, "train", "test"
    )
    numeric_columns = [
        "delivery_person_age",
        "delivery_person_ratings",
        "vehicle_condition",
        "multiple_deliveries",
        "distance_km",
        "hour_sin",
        "hour_cos",
        "day_of_week",
    ]
    target = "delivery_time_min"
    return frame[numeric_columns + categorical_columns + [target, "dataset_split"]], temporal_cutoff


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--metadata", required=True)
    args = parser.parse_args()

    dataset_path = resolve_dataset(Path(args.data))
    prepared_pdf, temporal_cutoff = prepare_data(dataset_path)

    spark = SparkSession.builder.appName("Train-Food-Delivery-Time-RF").getOrCreate()
    spark.sparkContext.setLogLevel("WARN")
    try:
        prepared = spark.createDataFrame(prepared_pdf)
        train_data = prepared.filter("dataset_split = 'train'").drop("dataset_split")
        test_data = prepared.filter("dataset_split = 'test'").drop("dataset_split")
        train_count = train_data.count()
        test_count = test_data.count()

        numeric_columns = [
            "delivery_person_age",
            "delivery_person_ratings",
            "vehicle_condition",
            "multiple_deliveries",
            "distance_km",
            "hour_sin",
            "hour_cos",
            "day_of_week",
        ]
        categorical_columns = [
            "weather_conditions",
            "road_traffic_density",
            "type_of_order",
            "type_of_vehicle",
            "festival",
            "city",
        ]
        target = "delivery_time_min"
        imputed_columns = [f"{column}_imp" for column in numeric_columns]
        stages = [
            Imputer(
                inputCols=numeric_columns,
                outputCols=imputed_columns,
                strategy="median",
            )
        ]
        stages.extend(
            StringIndexer(
                inputCol=column,
                outputCol=f"{column}_idx",
                handleInvalid="keep",
            )
            for column in categorical_columns
        )
        stages.extend(
            OneHotEncoder(
                inputCol=f"{column}_idx",
                outputCol=f"{column}_vec",
                handleInvalid="keep",
            )
            for column in categorical_columns
        )
        stages.extend(
            [
                VectorAssembler(
                    inputCols=imputed_columns
                    + [f"{column}_vec" for column in categorical_columns],
                    outputCol="features",
                    handleInvalid="keep",
                ),
                RandomForestRegressor(
                    labelCol=target,
                    featuresCol="features",
                    numTrees=100,
                    maxDepth=10,
                    minInstancesPerNode=3,
                    featureSubsetStrategy="0.8",
                    seed=SEED,
                ),
            ]
        )
        model = Pipeline(stages=stages).fit(train_data)
        predictions = model.transform(test_data)

        rmse_evaluator = RegressionEvaluator(
            labelCol=target, predictionCol="prediction", metricName="rmse"
        )
        mae_evaluator = RegressionEvaluator(
            labelCol=target, predictionCol="prediction", metricName="mae"
        )
        r2_evaluator = RegressionEvaluator(
            labelCol=target, predictionCol="prediction", metricName="r2"
        )
        rmse = rmse_evaluator.evaluate(predictions)
        mae = mae_evaluator.evaluate(predictions)
        r2 = r2_evaluator.evaluate(predictions)
        train_mean = train_data.selectExpr(f"avg({target}) AS mean_target").first()[
            "mean_target"
        ]
        baseline = test_data.withColumn("prediction", lit(float(train_mean)))
        baseline_rmse = rmse_evaluator.evaluate(baseline)
        if rmse >= baseline_rmse:
            raise RuntimeError("El modelo no supera la referencia de la media")

        model.write().overwrite().save(args.out)
        metadata = {
            "model": "RandomForestRegressor",
            "target": target,
            "dataset": DATASET_SLUG,
            "raw_rows": EXPECTED_ROWS,
            "clean_rows": len(prepared_pdf),
            "train_rows": train_count,
            "test_rows": test_count,
            "temporal_cutoff": temporal_cutoff.date().isoformat(),
            "rmse": rmse,
            "mae": mae,
            "r2": r2,
            "baseline_mean_rmse": baseline_rmse,
            "seed": SEED,
        }
        metadata_path = Path(args.metadata)
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        print(
            f"[METRICS] RF RMSE={rmse:.3f}, MAE={mae:.3f}, R2={r2:.3f}; "
            f"media RMSE={baseline_rmse:.3f}"
        )
        print(f"[OK] Modelo guardado en {args.out}")
        print(f"[OK] Metadatos guardados en {args.metadata}")
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
