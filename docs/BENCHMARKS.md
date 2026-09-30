# Verified Benchmarks

Measured 2026-09-26 on the local Windows development workstation using the MIMIC-IV Clinical Database Demo subset present in the repository. These numbers are not full-dataset or production capacity claims.

## Data pipeline

| Measurement | Result |
|---|---:|
| Engine | Pandas local/CI profile |
| Raw patients | 100 |
| Raw admissions | 275 |
| Eligible readmission rows | 260 |
| Patient-360 rows | 100 |
| End-to-end runtime | 0.721 s |
| Raw input throughput | 520.1 rows/s |
| Critical DQ failures | 0 / 4 rules |

Spark read execution was verified locally, but Windows Parquet writes require a trusted Hadoop `winutils.exe`; Spark write benchmarks are intentionally not reported. The Docker/Linux Spark path remains the full-scale target.

## Readmission baseline

MLflow run: `68cd8ae717004a6e86e12604007eb23d`. Logistic regression, patient-disjoint stratified split, 74 held-out rows from 14 patients.

| Metric | Result |
|---|---:|
| ROC-AUC | 0.5523 |
| PR-AUC | 0.2979 |
| Precision | 0.1857 |
| Recall / sensitivity | 1.0000 |
| Specificity | 0.0656 |
| F1 | 0.3133 |
| Brier score | 0.1987 |
| Training + tracking runtime | 18.411 s |

The selected threshold is 0.10. Performance is weak and not clinically deployable; it demonstrates a reproducible, leakage-aware evaluation path on a small demo cohort.

## Retrieval

Sentence Transformer `all-MiniLM-L6-v2`, 275 provenance-bearing admission documents, 384-dimensional FAISS inner-product index, nine admission-type evaluation queries.

| Metric | Result |
|---|---:|
| Precision@5 | 0.7778 |
| Recall@5 | 0.1615 |
| MRR | 0.7778 |
| NDCG@5 | 0.7778 |
| Mean query latency | 24.86 ms |
| Index build runtime | 14.343 s |

## API

Local Uvicorn, single process, 30 sequential prediction requests after startup.

| Metric | Result |
|---|---:|
| Prediction p50 | 30.536 ms |
| Prediction p95 | 52.620 ms |
| Prediction maximum | 120.959 ms |
| Health / readiness / search / metrics smoke | HTTP 200 |

This is a smoke benchmark, not a load or concurrency benchmark.
