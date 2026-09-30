# Data Model

- **Raw:** immutable permitted `.csv.gz` files under `data/raw/{hosp,icu}`.
- **Bronze:** source-aligned Parquet with ingestion timestamp, source filename, SHA-256, and run ID.
- **Silver patients:** one row per `subject_id`; validated gender, age, and anchor year.
- **Silver admissions:** one row per `hadm_id`; normalized timestamps and valid encounter intervals.
- **Quarantine:** rejected source rows plus `_rejection_reason`; never silently discarded.
- **Gold patient_360:** one row per patient with admission count and longitudinal bounds.
- **Gold readmission_features:** one eligible discharge per `hadm_id`, prediction cutoff at discharge, prior-only features, and next-admission-derived label.

Operational PostgreSQL schemas are `bronze`, `silver`, `gold`, `ml`, and `audit`. Alembic owns metadata table evolution; lake data remains Parquet.
