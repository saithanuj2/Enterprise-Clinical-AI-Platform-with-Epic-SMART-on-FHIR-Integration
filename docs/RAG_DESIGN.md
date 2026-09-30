# Retrieval and RAG Design

Each Silver admission becomes a document with subject/admission provenance. Sentence Transformers creates normalized embeddings stored in FAISS. Retrieval evaluation is separate from response composition and records Precision@K, Recall@K, MRR, NDCG, and latency.

The current response composer is deliberately extractive: it returns evidence text and citations or an explicit insufficient-evidence response. It does not pretend a hosted LLM is configured. On Windows API worker threads, a normalized TF-IDF FAISS fallback avoids an observed Torch DLL initialization problem; Linux/container deployments use the persisted Sentence-Transformer FAISS index.

No raw PHI or unrestricted external medical content is indexed.
