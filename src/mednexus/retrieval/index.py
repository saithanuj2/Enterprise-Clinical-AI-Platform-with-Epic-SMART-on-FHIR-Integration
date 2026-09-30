"""Sentence-Transformer embeddings and FAISS search for deidentified demo records."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import faiss
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer

DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


@dataclass(frozen=True)
class ClinicalDocument:
    document_id: str
    text: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class SearchResult:
    document_id: str
    text: str
    score: float
    metadata: dict[str, Any]


def build_documents(project_root: Path) -> list[ClinicalDocument]:
    admissions = pd.read_parquet(project_root / "data" / "silver" / "admissions")
    documents: list[ClinicalDocument] = []
    for row in admissions.itertuples(index=False):
        document_id = f"admission-{int(str(row.hadm_id))}"
        text = (
            f"Hospital admission type {row.admission_type}. "
            f"Admission location {row.admission_location}. "
            f"Discharge location {row.discharge_location}. "
            f"Insurance {row.insurance}. Race {row.race}. "
            f"Admitted {row.admittime} and discharged {row.dischtime}."
        )
        documents.append(
            ClinicalDocument(
                document_id=document_id,
                text=text,
                metadata={
                    "source": "silver.admissions",
                    "subject_id": int(str(row.subject_id)),
                    "hadm_id": int(str(row.hadm_id)),
                    "admission_type": str(row.admission_type),
                },
            )
        )
    return documents


def build_index(project_root: Path, model_name: str = DEFAULT_MODEL) -> dict[str, Any]:
    from sentence_transformers import SentenceTransformer

    started = time.perf_counter()
    documents = build_documents(project_root)
    if not documents:
        raise ValueError("Cannot build retrieval index without clinical documents")
    model = SentenceTransformer(model_name)
    embeddings = model.encode(
        [document.text for document in documents],
        normalize_embeddings=True,
        show_progress_bar=False,
    ).astype("float32")
    index = faiss.IndexFlatIP(embeddings.shape[1])
    index.add(embeddings)
    output = project_root / "artifacts" / "retrieval"
    output.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(output / "clinical.faiss"))
    (output / "documents.json").write_text(
        json.dumps([asdict(document) for document in documents], indent=2), encoding="utf-8"
    )
    report = {
        "model": model_name,
        "documents": len(documents),
        "dimensions": int(embeddings.shape[1]),
        "build_seconds": round(time.perf_counter() - started, 3),
    }
    (output / "metadata.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


class ClinicalRetriever:
    def __init__(self, project_root: Path, encoder: str = "transformer") -> None:
        directory = project_root / "artifacts" / "retrieval"
        metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
        self._documents = [
            ClinicalDocument(**item)
            for item in json.loads((directory / "documents.json").read_text(encoding="utf-8"))
        ]
        self._encoder = encoder
        self._model: Any = None
        self._vectorizer: TfidfVectorizer | None = None
        if encoder == "transformer":
            from sentence_transformers import SentenceTransformer

            self._index = faiss.read_index(str(directory / "clinical.faiss"))
            self._model = SentenceTransformer(metadata["model"])
        elif encoder == "lexical":
            self._vectorizer = TfidfVectorizer(ngram_range=(1, 2), min_df=1)
            matrix = self._vectorizer.fit_transform(
                [document.text for document in self._documents]
            ).astype("float32")
            dense = np.asarray(matrix.toarray(), dtype="float32")
            faiss.normalize_L2(dense)
            self._index = faiss.IndexFlatIP(dense.shape[1])
            self._index.add(dense)
        else:
            raise ValueError("encoder must be 'transformer' or 'lexical'")

    def search(self, query: str, limit: int = 5, subject_id: int | None = None) -> list[SearchResult]:
        if not query.strip():
            raise ValueError("query must not be empty")
        candidate_limit = min(len(self._documents), max(limit * 10, limit))
        if self._encoder == "transformer":
            query_embedding = self._model.encode(
                [query], normalize_embeddings=True, show_progress_bar=False
            ).astype("float32")
        else:
            if self._vectorizer is None:
                raise RuntimeError("lexical encoder is not initialized")
            query_embedding = np.asarray(
                self._vectorizer.transform([query]).toarray(), dtype="float32"
            )
            faiss.normalize_L2(query_embedding)
        scores, indices = self._index.search(query_embedding, candidate_limit)
        results: list[SearchResult] = []
        for score, index in zip(scores[0], indices[0], strict=True):
            if index < 0:
                continue
            document = self._documents[int(index)]
            if subject_id is not None and document.metadata.get("subject_id") != subject_id:
                continue
            results.append(
                SearchResult(document.document_id, document.text, float(score), document.metadata)
            )
            if len(results) == limit:
                break
        return results


def evaluate_retrieval(project_root: Path, limit: int = 5) -> dict[str, float]:
    """Evaluate clinical-category retrieval separately from response composition."""

    retriever = ClinicalRetriever(project_root)
    documents = build_documents(project_root)
    reciprocal_ranks: list[float] = []
    recalls: list[float] = []
    precisions: list[float] = []
    ndcgs: list[float] = []
    latencies: list[float] = []
    admission_types = sorted({str(document.metadata["admission_type"]) for document in documents})
    for admission_type in admission_types:
        relevant = {
            document.document_id
            for document in documents
            if document.metadata["admission_type"] == admission_type
        }
        query = f"hospital admissions with admission type {admission_type}"
        started = time.perf_counter()
        results = retriever.search(query, limit=limit)
        latencies.append(1000 * (time.perf_counter() - started))
        ids = [result.document_id for result in results]
        relevance = [1 if document_id in relevant else 0 for document_id in ids]
        hits = sum(relevance)
        precisions.append(hits / limit)
        recalls.append(hits / len(relevant))
        first_hit = next((index + 1 for index, value in enumerate(relevance) if value), None)
        reciprocal_ranks.append(1.0 / first_hit if first_hit else 0.0)
        dcg = sum(value / np.log2(index + 2) for index, value in enumerate(relevance))
        ideal_hits = min(limit, len(relevant))
        idcg = sum(1.0 / np.log2(index + 2) for index in range(ideal_hits))
        ndcgs.append(float(dcg / idcg) if idcg else 0.0)
    report = {
        f"recall_at_{limit}": float(np.mean(recalls)),
        f"precision_at_{limit}": float(np.mean(precisions)),
        "mrr": float(np.mean(reciprocal_ranks)),
        f"ndcg_at_{limit}": float(np.mean(ndcgs)),
        "mean_latency_ms": float(np.mean(latencies)),
        "queries": float(len(admission_types)),
    }
    output = project_root / "artifacts" / "retrieval" / "evaluation.json"
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def grounded_answer(query: str, evidence: list[SearchResult], minimum_score: float = 0.2) -> dict[str, Any]:
    supported = [item for item in evidence if item.score >= minimum_score]
    if not supported:
        return {
            "answer": "Insufficient indexed evidence to answer this question.",
            "citations": [],
            "grounded": False,
        }
    citations = [
        {"document_id": item.document_id, "score": item.score, **item.metadata}
        for item in supported
    ]
    answer = "Relevant indexed evidence: " + " ".join(item.text for item in supported[:3])
    return {"answer": answer, "citations": citations, "grounded": True, "query": query}
