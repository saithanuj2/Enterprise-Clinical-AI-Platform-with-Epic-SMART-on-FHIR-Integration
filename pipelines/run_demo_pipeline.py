"""Run the verified MIMIC demo vertical slice from the repository root."""

import argparse
import os
from pathlib import Path

from mednexus.data.local_pipeline import run_local_demo_pipeline
from mednexus.data.pipeline import run_demo_pipeline

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", choices=("auto", "spark", "pandas"), default="auto")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    use_pandas = args.engine == "pandas" or (
        args.engine == "auto" and os.name == "nt" and not os.environ.get("HADOOP_HOME")
    )
    result = run_local_demo_pipeline(root) if use_pandas else run_demo_pipeline(root)
    print(
        f"run_id={result.run_id} status={result.status} "
        f"duration_seconds={result.duration_seconds}"
    )
    for profile in result.profiles:
        print(
            f"{profile.layer}.{profile.dataset}: rows={profile.rows} "
            f"columns={profile.columns} duplicates={profile.duplicate_rows}"
        )
