"""Build and evaluate the clinical FAISS index."""

from pathlib import Path

from mednexus.retrieval.index import build_index, evaluate_retrieval

if __name__ == "__main__":
    root = Path(__file__).resolve().parents[2]
    print(build_index(root))
    print(evaluate_retrieval(root))
