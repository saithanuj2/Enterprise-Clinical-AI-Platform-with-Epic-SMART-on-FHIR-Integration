import argparse
import os
import sys
from pathlib import Path
from uuid import uuid4

from pyspark.sql import SparkSession
from pyspark.sql.functions import current_timestamp, input_file_name, lit
from sqlalchemy import create_engine, text

from mednexus.config import get_settings
from mednexus.ingestion.registry import DatasetConfig, load_registry

ROOT = Path(__file__).resolve().parents[2]


def build_spark():
    python_executable = sys.executable

    os.environ["PYSPARK_PYTHON"] = python_executable
    os.environ["PYSPARK_DRIVER_PYTHON"] = python_executable

    return (
        SparkSession.builder
        .appName("MedNexus-Bronze-Ingestion")
        .master("local[*]")
        .config("spark.sql.shuffle.partitions", "8")
        .config("spark.pyspark.python", python_executable)
        .config("spark.pyspark.driver.python", python_executable)
        .getOrCreate()
    )


def start_pipeline_run(engine, pipeline_name):
    run_id = str(uuid4())

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO audit.pipeline_runs (
                    run_id,
                    pipeline_name,
                    status
                )
                VALUES (
                    :run_id,
                    :pipeline_name,
                    'RUNNING'
                )
                """
            ),
            {
                "run_id": run_id,
                "pipeline_name": pipeline_name,
            },
        )

    return run_id


def complete_pipeline_run(
    engine,
    run_id,
    status,
    records_processed=0,
    records_failed=0,
):
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                UPDATE audit.pipeline_runs
                SET
                    status = :status,
                    completed_at = NOW(),
                    records_processed = :records_processed,
                    records_failed = :records_failed
                WHERE run_id = :run_id
                """
            ),
            {
                "run_id": run_id,
                "status": status,
                "records_processed": records_processed,
                "records_failed": records_failed,
            },
        )


def validate_required_columns(df, required_columns):
    missing = [
        column
        for column in required_columns
        if column not in df.columns
    ]

    if missing:
        raise ValueError(
            f"Missing required columns: {missing}"
        )


def ingest_dataset(spark, engine, dataset_name: str, config: DatasetConfig):
    pipeline_name = f"bronze_ingestion_{dataset_name}"

    run_id = start_pipeline_run(
        engine,
        pipeline_name,
    )

    raw_path = (
        ROOT
        / "data"
        / "raw"
        / config.source_module
        / config.source_file
    )

    bronze_path = ROOT / config.bronze_path

    print("=" * 70)
    print(f"Dataset: {dataset_name}")
    print(f"Source:  {raw_path}")
    print(f"Target:  {bronze_path}")
    print("=" * 70)

    try:
        if not raw_path.exists():
            raise FileNotFoundError(
                f"Source file not found: {raw_path}"
            )

        df = (
            spark.read
            .option("header", True)
            .option("inferSchema", True)
            .csv(str(raw_path))
        )

        validate_required_columns(
            df,
            config.required_columns,
        )

        row_count = df.count()

        bronze_df = (
            df
            .withColumn(
                "_ingested_at",
                current_timestamp(),
            )
            .withColumn(
                "_source_file",
                input_file_name(),
            )
            .withColumn(
                "_pipeline_run_id",
                lit(run_id),
            )
        )

        (
            bronze_df.write
            .mode("overwrite")
            .parquet(str(bronze_path))
        )

        complete_pipeline_run(
            engine,
            run_id,
            "SUCCESS",
            records_processed=row_count,
        )

        print(
            f"SUCCESS: {dataset_name} -> "
            f"{row_count:,} records"
        )

    except Exception:
        complete_pipeline_run(
            engine,
            run_id,
            "FAILED",
        )
        raise


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--dataset",
        required=True,
        help="Dataset name from dataset_registry.yaml",
    )

    args = parser.parse_args()

    registry_path = ROOT / "pipelines" / "ingestion" / "dataset_registry.yaml"
    registry = load_registry(registry_path)

    if args.dataset not in registry:
        raise ValueError(
            f"Unknown dataset: {args.dataset}. "
            f"Available: {list(registry.keys())}"
        )

    settings = get_settings()

    engine = create_engine(
        settings.database_url
    )

    spark = build_spark()
    spark.sparkContext.setLogLevel("WARN")

    try:
        ingest_dataset(
            spark,
            engine,
            args.dataset,
            registry[args.dataset],
        )
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
