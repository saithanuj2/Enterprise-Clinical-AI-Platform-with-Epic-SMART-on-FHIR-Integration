# Readmission ML Design

The baseline predicts whether another admission begins 0–30 days after discharge. In-hospital deaths are excluded. Features are limited to age at admission, current length of stay, prior admission count, gender, admission type, and insurance, all available by the discharge prediction cutoff.

Patients are assigned to exactly one train, validation, or test split. Logistic regression uses class weighting, one-hot encoding, scaling, and median/mode imputation. `C` and the operating threshold are selected on validation data; the test set is touched once. PR-AUC is primary because the cohort is imbalanced. MLflow records parameters, dataset SHA-256, features, metrics, and the model artifact.

Demo performance is weak and must not support clinical deployment. Future work requires more domains, temporal validation on full MIMIC, subgroup analysis, calibration plots, and external validation.
