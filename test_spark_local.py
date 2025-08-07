from pyspark.sql import SparkSession

print("Creando SparkSession en modo local...")

spark = (
    SparkSession.builder
    .appName("TestLocal")
    .master("local[*]")  # 👈 modo local
    .getOrCreate()
)

print("✅ SparkSession local creada")
print(spark.range(5).toPandas())
