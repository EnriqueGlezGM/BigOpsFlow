import argparse
import re
from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col, lower, regexp_extract, when, hour, date_format, dayofweek, to_timestamp, lit,
    regexp_replace, trim, length, expr
)
from pyspark.ml.feature import StringIndexer, OneHotEncoder, VectorAssembler
from pyspark.ml.regression import GBTRegressor
from pyspark.ml import Pipeline
from pyspark.ml.evaluation import RegressionEvaluator


def safe_col(name: str):
    """
    Return a Column that safely references `name` even if it contains special chars
    like spaces, slashes, or parentheses.
    """
    if re.search(r"[^a-zA-Z0-9_]", name):
        return col(f"`{name}`")
    return col(name)


def resolve_name(df, candidates):
    """
    Given a DataFrame and a list of candidate column names (possible variants),
    return the *actual* column name found in df (case-insensitive).
    """
    idx = {c.lower(): c for c in df.columns}
    for cand in candidates:
        real = idx.get(cand.lower())
        if real is not None:
            return real
    return None


def ensure_or_default(df, candidates, default_lit):
    """
    Try to resolve a column name, otherwise create a new column with a default literal value.
    Returns (df_with_column, actual_column_name)
    """
    found = resolve_name(df, candidates)
    if found is not None:
        return df, found
    # create it with the *first* candidate name for later reference
    placeholder = candidates[0]
    return df.withColumn(placeholder, default_lit), placeholder


def to_double_clean(name: str):
    """
    Limpia símbolos y convierte a DOUBLE tolerando '', 'NA', 'None', etc.
    - Quita cualquier carácter no numérico (excepto . y -).
    - Si queda vacío, devuelve NULL (double).
    """
    cleaned = regexp_replace(safe_col(name), r"[^0-9\\.-]", "")
    return when(trim(cleaned) == "", lit(None).cast("double")).otherwise(cleaned.cast("double"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, help="Ruta del CSV de entrada (en el PVC montado)")
    ap.add_argument("--out",  required=True, help="Ruta de salida para guardar el PipelineModel (en el PVC montado)")
    ap.add_argument("--master", default=None, help="URL master Spark (opcional si ya se pasa en spark-submit)")
    ap.add_argument("--datefmt", default="yyyy-MM-dd HH:mm:ss", help="Formato de fechas si vienen como string")
    args = ap.parse_args()

    builder = SparkSession.builder.appName("train-gbt")
    if args.master:
        builder = builder.master(args.master)

    spark = builder.getOrCreate()
    spark.sparkContext.setLogLevel("WARN")

    # === Carga del dataset ===
    df = (
        spark.read
        .option("header", True)
        .option("inferSchema", True)
        .csv(args.data)
    )

    # === Resolver nombres de columnas (snake_case vs nombres con espacios) ===
    # Mapeos de posibles variantes a nombres canónicos
    c_order_dt     = resolve_name(df, ["Order Date and Time", "order_date_and_time", "order_datetime", "order_date"])
    c_delivery_dt  = resolve_name(df, ["Delivery Date and Time", "delivery_date_and_time", "delivery_datetime", "delivery_date"])
    c_discounts    = resolve_name(df, ["Discounts and Offers", "discounts_and_offers", "discounts_offers"])
    c_payment_meth = resolve_name(df, ["Payment Method", "payment_method"])
    c_order_val    = resolve_name(df, ["Order Value", "order_value"])
    c_delivery_fee = resolve_name(df, ["Delivery Fee", "delivery_fee"])
    c_comm_fee     = resolve_name(df, ["Commission Fee", "commission_fee"])
    c_pay_proc_fee = resolve_name(df, ["Payment Processing Fee", "payment_processing_fee"])

    # Esta a veces viene con slash en el nombre
    df, c_refunds = ensure_or_default(df, ["Refunds/Chargebacks", "refunds/chargebacks", "refunds_chargebacks"], lit(0.0))

    required = {
        "Order Date and Time / order_date_and_time": c_order_dt,
        "Delivery Date and Time / delivery_date_and_time": c_delivery_dt,
        "Order Value / order_value": c_order_val,
        "Delivery Fee / delivery_fee": c_delivery_fee,
        "Payment Method / payment_method": c_payment_meth,
        "Discounts and Offers / discounts_and_offers": c_discounts,
        "Commission Fee / commission_fee": c_comm_fee,
        "Payment Processing Fee / payment_processing_fee": c_pay_proc_fee,
    }
    missing = [k for k, v in required.items() if v is None]
    if missing:
        cols = ", ".join(df.columns)
        raise ValueError(
            f"No se encuentran columnas requeridas: {missing}. "
            f"Columnas disponibles en el CSV: {cols}"
        )

    # === Saneado de columnas numéricas que pueden venir como string/currency ===
    df = (
        df
        .withColumn("order_value_dbl",              to_double_clean(c_order_val))
        .withColumn("delivery_fee_dbl",             to_double_clean(c_delivery_fee))
        .withColumn("commission_fee_dbl",           to_double_clean(c_comm_fee))
        .withColumn("payment_processing_fee_dbl",   to_double_clean(c_pay_proc_fee))
        .withColumn("refunds_chargebacks_dbl",      to_double_clean(c_refunds))
    )

    # === Descuentos: extrae números y castea de forma tolerante (try_cast) ===
    df = (
        df
        .withColumn("disc_pct_str", regexp_extract(lower(safe_col(c_discounts)), r"(\d+)%", 1))
        .withColumn("disc_abs_str", regexp_extract(lower(safe_col(c_discounts)), r"(\d+)", 1))
        .withColumn("disc_pct",     expr("try_cast(disc_pct_str as double)"))
        .withColumn("disc_abs",     expr("try_cast(disc_abs_str as double)"))
    )

    # === Derivadas base ===
    odt_ts = to_timestamp(safe_col(c_order_dt), args.datefmt)
    ddt_ts = to_timestamp(safe_col(c_delivery_dt), args.datefmt)

    df = (
        df
        .withColumn("delivery_duration_min", (ddt_ts.cast("long") - odt_ts.cast("long")) / 60.0)
        .withColumn("day_of_week",  date_format(odt_ts, "EEEE"))  # Lunes, Martes, ...
        .withColumn("hour_of_day",  hour(odt_ts))
    )

    # Indicadores / flags robustos
    df = (
        df
        .withColumn(
            "has_discount",
            when(trim(lower(safe_col(c_discounts))).isin("", "none", "no discount", "no discounts"), 0).otherwise(1)
        )
        .withColumn("refunded", when(col("refunds_chargebacks_dbl") > 0, 1).otherwise(0))
        .withColumn("es_fin_de_semana", when(dayofweek(odt_ts).isin(1, 7), 1).otherwise(0))  # 1=Domingo, 7=Sábado
        .withColumn(
            "es_hora_punta",
            when(
                (col("hour_of_day").between(13, 15)) | (col("hour_of_day").between(20, 22)),
                1
            ).otherwise(0)
        )
    )

    # Descuento aproximado (prioriza %; si no, absoluto tipo "NN off")
    df = df.withColumn(
        "discount_value",
        when(col("disc_pct").isNotNull(), col("order_value_dbl") * (col("disc_pct") / 100.0))
        .when(lower(safe_col(c_discounts)).contains("off") & col("disc_abs").isNotNull(), col("disc_abs"))
        .otherwise(lit(0.0))
    )

    # Categóricas y numéricas
    categorical = ["day_of_week", "hour_of_day_str", c_payment_meth, c_discounts]
    df = df.withColumn("hour_of_day_str", col("hour_of_day").cast("string"))

    numeric = [
        "order_value_dbl", "delivery_fee_dbl", "commission_fee_dbl", "payment_processing_fee_dbl",
        "discount_value", "has_discount", "refunded",
        "es_fin_de_semana", "es_hora_punta"
    ]

    df = df.drop("disc_pct_str", "disc_abs_str")

    # Indexación + OneHot
    indexers = [StringIndexer(inputCol=c, outputCol=f"{c}_idx", handleInvalid="keep") for c in categorical]
    encoders = [OneHotEncoder(inputCol=f"{c}_idx", outputCol=f"{c}_vec") for c in categorical]

    assembler = VectorAssembler(
        inputCols=[*numeric] + [f"{c}_vec" for c in categorical],
        outputCol="features"
    )

    reg = GBTRegressor(featuresCol="features", labelCol="delivery_duration_min", maxDepth=5, maxIter=40)
    pipe = Pipeline(stages=indexers + encoders + [assembler, reg])

    # Train / Test
    train, test = df.na.drop(subset=["delivery_duration_min"]).randomSplit([0.8, 0.2], seed=42)
    model = pipe.fit(train)

    preds = model.transform(test)
    rmse = RegressionEvaluator(
        labelCol="delivery_duration_min", predictionCol="prediction", metricName="rmse"
    ).evaluate(preds)
    print(f"[INFO] RMSE: {rmse:.2f}")

    # Guardado del PipelineModel en PVC
    model.write().overwrite().save(args.out)
    print(f"[OK] Modelo guardado en: {args.out}")

    spark.stop()


if __name__ == "__main__":
    main()