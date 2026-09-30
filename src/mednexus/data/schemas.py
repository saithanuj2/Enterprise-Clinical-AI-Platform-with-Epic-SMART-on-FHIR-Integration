"""Explicit schemas for the MIMIC-IV demo tables currently supported end to end."""

from pyspark.sql.types import IntegerType, LongType, StringType, StructField, StructType

PATIENTS_SCHEMA = StructType(
    [
        StructField("subject_id", LongType(), True),
        StructField("gender", StringType(), True),
        StructField("anchor_age", IntegerType(), True),
        StructField("anchor_year", IntegerType(), True),
        StructField("anchor_year_group", StringType(), True),
        StructField("dod", StringType(), True),
    ]
)

ADMISSIONS_SCHEMA = StructType(
    [
        StructField("subject_id", LongType(), True),
        StructField("hadm_id", LongType(), True),
        StructField("admittime", StringType(), True),
        StructField("dischtime", StringType(), True),
        StructField("deathtime", StringType(), True),
        StructField("admission_type", StringType(), True),
        StructField("admit_provider_id", StringType(), True),
        StructField("admission_location", StringType(), True),
        StructField("discharge_location", StringType(), True),
        StructField("insurance", StringType(), True),
        StructField("language", StringType(), True),
        StructField("marital_status", StringType(), True),
        StructField("race", StringType(), True),
        StructField("edregtime", StringType(), True),
        StructField("edouttime", StringType(), True),
        StructField("hospital_expire_flag", IntegerType(), True),
    ]
)

SCHEMAS = {"patients": PATIENTS_SCHEMA, "admissions": ADMISSIONS_SCHEMA}
