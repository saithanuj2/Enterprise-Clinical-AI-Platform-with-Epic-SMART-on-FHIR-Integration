import os
import sys

from pyspark.sql import SparkSession


def main():
    # Force Spark driver and workers to use this exact Python environment.
    python_executable = sys.executable

    os.environ["PYSPARK_PYTHON"] = python_executable
    os.environ["PYSPARK_DRIVER_PYTHON"] = python_executable

    print(f"Driver Python: {python_executable}")
    print(f"Driver Python version: {sys.version.split()[0]}")
    print(f"PYSPARK_PYTHON: {os.environ['PYSPARK_PYTHON']}")

    spark = (
        SparkSession.builder
        .appName("MedNexus-Spark-Smoke-Test")
        .master("local[*]")
        .config("spark.sql.shuffle.partitions", "4")
        .config("spark.pyspark.python", python_executable)
        .config("spark.pyspark.driver.python", python_executable)
        .getOrCreate()
    )

    spark.sparkContext.setLogLevel("ERROR")

    data = [
        ("P001", 65, "M"),
        ("P002", 52, "F"),
        ("P003", 71, "F"),
    ]

    df = spark.createDataFrame(
        data,
        ["patient_id", "age", "gender"],
    )

    print("\nMedNexus test dataset:")
    df.show()

    print(f"Rows: {df.count()}")
    print(f"Spark version: {spark.version}")

    worker_python_version = (
        spark.sparkContext
        .parallelize([1], 1)
        .map(lambda _: __import__("sys").version.split()[0])
        .collect()[0]
    )

    print(f"Worker Python version: {worker_python_version}")

    driver_major_minor = ".".join(sys.version.split()[0].split(".")[:2])
    worker_major_minor = ".".join(worker_python_version.split(".")[:2])

    assert worker_major_minor == driver_major_minor, (
        "Spark driver/worker Python mismatch: "
        f"driver={driver_major_minor}, worker={worker_major_minor}"
    )

    spark.stop()

    print("\nMedNexus Spark environment OK")


if __name__ == "__main__":
    main()
