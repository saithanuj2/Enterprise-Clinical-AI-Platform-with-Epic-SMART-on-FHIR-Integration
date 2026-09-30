"""Patient-disjoint 30-day readmission baseline and artifact lifecycle."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

NUMERIC_FEATURES = ["age_at_admission", "length_of_stay_days", "prior_admissions"]
CATEGORICAL_FEATURES = ["gender", "admission_type", "insurance"]
MODEL_FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES
TARGET = "readmitted_30d"


@dataclass(frozen=True)
class SplitSummary:
    rows: int
    patients: int
    positives: int


@dataclass(frozen=True)
class TrainingReport:
    run_id: str
    dataset_sha256: str
    trained_at: str
    duration_seconds: float
    selected_c: float
    threshold: float
    metrics: dict[str, float]
    splits: dict[str, SplitSummary]
    model_path: str


def dataset_digest(dataset_path: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(dataset_path.rglob("*.parquet")):
        digest.update(path.name.encode())
        with path.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
    return digest.hexdigest()


def patient_disjoint_split(
    frame: pd.DataFrame, seed: int = 42
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Split by patient, stratifying on whether each patient has any positive admission."""

    patient_labels = frame.groupby("subject_id")[TARGET].max().reset_index()
    rng = np.random.default_rng(seed)
    train_ids: list[Any] = []
    validation_ids: list[Any] = []
    test_ids: list[Any] = []
    for _, group in patient_labels.groupby(TARGET):
        ids = group["subject_id"].to_numpy(copy=True)
        rng.shuffle(ids)
        test_count = max(1, round(len(ids) * 0.15))
        validation_count = max(1, round(len(ids) * 0.15))
        test_ids.extend(ids[:test_count])
        validation_ids.extend(ids[test_count : test_count + validation_count])
        train_ids.extend(ids[test_count + validation_count :])
    train = frame[frame["subject_id"].isin(train_ids)].copy()
    validation = frame[frame["subject_id"].isin(validation_ids)].copy()
    test = frame[frame["subject_id"].isin(test_ids)].copy()
    return train, validation, test


def build_model(c_value: float = 1.0) -> Pipeline:
    numeric = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
        ]
    )
    categorical = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("encode", OneHotEncoder(handle_unknown="ignore")),
        ]
    )
    preprocessing = ColumnTransformer(
        [("numeric", numeric, NUMERIC_FEATURES), ("categorical", categorical, CATEGORICAL_FEATURES)]
    )
    return Pipeline(
        [
            ("preprocessing", preprocessing),
            (
                "classifier",
                LogisticRegression(
                    C=c_value,
                    class_weight="balanced",
                    max_iter=2000,
                    random_state=42,
                ),
            ),
        ]
    )


def choose_threshold(labels: pd.Series, probabilities: np.ndarray) -> float:
    candidates = np.linspace(0.1, 0.9, 81)
    scores = [f1_score(labels, probabilities >= threshold, zero_division=0) for threshold in candidates]
    return float(candidates[int(np.argmax(scores))])


def evaluate(labels: pd.Series, probabilities: np.ndarray, threshold: float) -> dict[str, float]:
    predictions = probabilities >= threshold
    tn, fp, fn, tp = confusion_matrix(labels, predictions, labels=[0, 1]).ravel()
    metrics = {
        "pr_auc": float(average_precision_score(labels, probabilities)),
        "precision": float(precision_score(labels, predictions, zero_division=0)),
        "recall_sensitivity": float(recall_score(labels, predictions, zero_division=0)),
        "f1": float(f1_score(labels, predictions, zero_division=0)),
        "specificity": float(tn / (tn + fp)) if (tn + fp) else 0.0,
        "brier_score": float(brier_score_loss(labels, probabilities)),
        "true_negatives": float(tn),
        "false_positives": float(fp),
        "false_negatives": float(fn),
        "true_positives": float(tp),
    }
    metrics["roc_auc"] = (
        float(roc_auc_score(labels, probabilities)) if labels.nunique() == 2 else float("nan")
    )
    return metrics


def _summary(frame: pd.DataFrame) -> SplitSummary:
    return SplitSummary(len(frame), frame["subject_id"].nunique(), int(frame[TARGET].sum()))


def train_readmission_model(project_root: Path) -> TrainingReport:
    import mlflow
    import mlflow.sklearn
    from mlflow.models import infer_signature

    started = time.perf_counter()
    dataset_path = project_root / "data" / "gold" / "readmission_features"
    frame = pd.read_parquet(dataset_path)
    if frame.empty or frame[TARGET].nunique() < 2:
        raise ValueError("Training requires a non-empty cohort containing both outcome classes")
    train, validation, test = patient_disjoint_split(frame)
    if any(split[TARGET].nunique() < 2 for split in (train, validation, test)):
        raise ValueError("Each patient-disjoint split must contain both outcome classes")

    best_model: Pipeline | None = None
    best_c = 0.0
    best_score = -1.0
    for c_value in (0.1, 1.0, 10.0):
        candidate = build_model(c_value)
        candidate.fit(train[MODEL_FEATURES], train[TARGET])
        probabilities = candidate.predict_proba(validation[MODEL_FEATURES])[:, 1]
        score = average_precision_score(validation[TARGET], probabilities)
        if score > best_score:
            best_model, best_c, best_score = candidate, c_value, float(score)
    if best_model is None:
        raise RuntimeError("Model selection did not produce a candidate")

    validation_probabilities = best_model.predict_proba(validation[MODEL_FEATURES])[:, 1]
    threshold = choose_threshold(validation[TARGET], validation_probabilities)
    test_probabilities = best_model.predict_proba(test[MODEL_FEATURES])[:, 1]
    metrics = evaluate(test[TARGET], test_probabilities, threshold)
    digest = dataset_digest(dataset_path)
    model_dir = project_root / "artifacts" / "models" / "readmission"
    model_dir.mkdir(parents=True, exist_ok=True)
    model_path = model_dir / "model.joblib"
    joblib.dump(best_model, model_path)

    mlflow.set_tracking_uri((project_root / "mlruns").resolve().as_uri())
    mlflow.set_experiment("mednexus-readmission-demo")
    with mlflow.start_run() as run:
        mlflow.log_params(
            {
                "model": "logistic_regression",
                "C": best_c,
                "threshold": threshold,
                "dataset_sha256": digest,
                "split": "patient_disjoint_stratified",
                "features": ",".join(MODEL_FEATURES),
            }
        )
        mlflow.log_metrics({key: value for key, value in metrics.items() if np.isfinite(value)})
        input_example = train[MODEL_FEATURES].head(3)
        signature = infer_signature(input_example, best_model.predict_proba(input_example))
        mlflow.sklearn.log_model(
            best_model,
            "model",
            input_example=input_example,
            signature=signature,
        )
        run_id = run.info.run_id

    report = TrainingReport(
        run_id=run_id,
        dataset_sha256=digest,
        trained_at=datetime.now(UTC).isoformat(),
        duration_seconds=round(time.perf_counter() - started, 3),
        selected_c=best_c,
        threshold=threshold,
        metrics=metrics,
        splits={
            "train": _summary(train),
            "validation": _summary(validation),
            "test": _summary(test),
        },
        model_path=str(model_path.relative_to(project_root)),
    )
    (model_dir / "metadata.json").write_text(
        json.dumps(asdict(report), indent=2, allow_nan=False), encoding="utf-8"
    )
    return report


def load_model(project_root: Path) -> tuple[Pipeline, dict[str, Any]]:
    model_dir = project_root / "artifacts" / "models" / "readmission"
    model = joblib.load(model_dir / "model.joblib")
    metadata = json.loads((model_dir / "metadata.json").read_text(encoding="utf-8"))
    return model, metadata
