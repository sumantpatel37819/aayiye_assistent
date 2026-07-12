# Embedding module — mxbai-embed-large via Ollama
# Dimensions: 1024
# Ollama locally chal raha hona chahiye: `ollama serve`

import numpy as np
import requests


OLLAMA_URL = "http://localhost:11434/api/embeddings"
OLLAMA_MODEL = "mxbai-embed-large"


def _get_embedding(text: str) -> np.ndarray:
    """Ollama API se single text ka embedding lo."""
    response = requests.post(
        OLLAMA_URL,
        json={"model": OLLAMA_MODEL, "prompt": text, "keep_alive": -1},
        timeout=60
    )
    response.raise_for_status()
    embedding = response.json()["embedding"]
    return np.array(embedding, dtype="float32")


def create_embedding(chunks: list) -> np.ndarray:
    """
    chunks: list of str
    Returns: np.ndarray of shape (N, 1024)
    """
    if not chunks:
        return np.array([])

    print(f"  Embedding bana raha hoon: {len(chunks)} chunks...")
    embeddings = []
    for i, chunk in enumerate(chunks):
        emb = _get_embedding(chunk)
        embeddings.append(emb)
        if (i + 1) % 10 == 0:
            print(f"  {i + 1}/{len(chunks)} chunks done...")

    return np.array(embeddings, dtype="float32")


def create_embedding_query(query: str) -> np.ndarray:
    """
    query: single string
    Returns: np.ndarray of shape (1024,)
    """
    return _get_embedding(query)