# test_spark_min.py
from pyspark.sql import SparkSession

print("Creando SparkSession...")
spark = (
    SparkSession.builder
    .appName("MinimalTest")
    .getOrCreate()
)
print("✅ SparkSession creada")
