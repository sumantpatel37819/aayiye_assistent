"""
FAISS index manager — disk pe persist karta hai.

Files:
  faiss_index.faiss          — FAISS vector index
  faiss_index_metadata.json  — chunk text + source store karta hai

Features:
  - Naya index create karo ya existing mein append karo
  - Similarity threshold se decide karo — relevant data hai ya nahi
"""

import json
from pathlib import Path

import faiss
import numpy as np

# Project root ke paas index files save karo
_BASE_DIR = Path(__file__).resolve().parent.parent
FAISS_INDEX_PATH = str(_BASE_DIR / "faiss_index.faiss")
METADATA_PATH    = str(_BASE_DIR / "faiss_index_metadata.json")

EMBEDDING_DIM = 1024  # mxbai-embed-large

# L2 distance threshold — isse zyada distance ho toh "relevant nahi"
# normalized embeddings ke liye ~0.5 ek accha starting point hai
SIMILARITY_THRESHOLD = 0.8


# ─────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────

def _load_metadata() -> dict:
    if Path(METADATA_PATH).exists():
        with open(METADATA_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_metadata(metadata: dict):
    with open(METADATA_PATH, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)


def _load_or_create_index() -> faiss.IndexFlatL2:
    if Path(FAISS_INDEX_PATH).exists():
        return faiss.read_index(FAISS_INDEX_PATH)
    return faiss.IndexFlatL2(EMBEDDING_DIM)


# ─────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────

def create_faiss_index(embeddings: np.ndarray, chunks: list, source: str = "web_text"):
    """
    Embeddings aur unke corresponding text chunks ko FAISS index mein add karo.
    Existing index mein append karta hai (overwrite nahi karta).

    Args:
        embeddings : np.ndarray shape (N, 384)
        chunks     : list of str, len == N
        source     : source label (URL ya query)
    """
    if embeddings is None or len(embeddings) == 0:
        print("⚠ Koi embedding nahi mili — FAISS update skip.")
        return

    embeddings = np.array(embeddings).astype("float32")

    if embeddings.ndim == 1:
        embeddings = embeddings.reshape(1, -1)

    index = _load_or_create_index()
    metadata = _load_metadata()

    start_idx = index.ntotal  # existing vectors ke baad se add karein

    index.add(embeddings)
    faiss.write_index(index, FAISS_INDEX_PATH)

    # ✅ Metadata mein actual TEXT store karo, embeddings nahi
    for i, chunk in enumerate(chunks):
        global_idx = start_idx + i
        metadata[str(global_idx)] = {
            "text": chunk,
            "source": source
        }

    _save_metadata(metadata)
    print(f"✅ FAISS: {len(chunks)} chunks add kiye gaye. Total vectors: {index.ntotal}")


def load_faiss_index(query_embedding: np.ndarray, k: int = 5):
    """
    Query embedding se relevant chunks dhundho.

    Returns:
        (relevant_chunks: list[str], min_distance: float)
        Agar index nahi hai ya threshold exceed ho toh ([], large_float)
    """
    if not Path(FAISS_INDEX_PATH).exists():
        print("ℹ FAISS index abhi tak bana nahi.")
        return [], float("inf")

    index = faiss.read_index(FAISS_INDEX_PATH)
    metadata = _load_metadata()

    if index.ntotal == 0:
        return [], float("inf")

    query_embedding = np.array([query_embedding]).astype("float32")
    actual_k = min(k, index.ntotal)
    D, I = index.search(query_embedding, actual_k)

    results = []
    min_dist = float("inf")

    for dist, idx in zip(D[0], I[0]):
        if idx == -1:
            continue
        if dist < min_dist:
            min_dist = dist
        item = metadata.get(str(idx))
        if item:
            results.append(item["text"])

    return results, float(min_dist)


def is_relevant(min_distance: float) -> bool:
    """Threshold check — kya FAISS mein relevant data hai?"""
    return min_distance < SIMILARITY_THRESHOLD