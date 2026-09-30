"""Train and evaluate the MedNexus readmission baseline."""

from pathlib import Path

from mednexus.ml.readmission import train_readmission_model

if __name__ == "__main__":
    root = Path(__file__).resolve().parents[2]
    report = train_readmission_model(root)
    print(f"mlflow_run_id={report.run_id}")
    print(f"duration_seconds={report.duration_seconds}")
    for name, value in sorted(report.metrics.items()):
        print(f"{name}={value:.6f}")
