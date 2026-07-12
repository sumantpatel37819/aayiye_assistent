"""
RAG Index — high-level interface for storing and querying the FAISS vector store.
"""

from vector_and_Ragservice.chunking import chunk_text
from vector_and_Ragservice.embedding import create_embedding, create_embedding_query
from vector_and_Ragservice.FAISS import create_faiss_index, load_faiss_index, is_relevant


def store_to_rag(texts: list, source: str = "web_text"):
    """
    Scraped texts ko chunk → embed → FAISS mein store karo.

    Args:
        texts  : list of str (scraped page texts)
        source : label karna ke liye (URL ya query string)
    """
    if not texts:
        print("⚠ Store ke liye koi text nahi mila.")
        return

    chunks = chunk_text(texts)
    if not chunks:
        print("⚠ Chunking se koi chunk nahi bana.")
        return

    print(f"📦 {len(chunks)} chunks bane. Embedding bana raha hoon...")
    embeddings = create_embedding(chunks)

    create_faiss_index(embeddings, chunks, source=source)
    print("💾 RAG store complete.")


def ask_query(query: str):
    """
    FAISS mein query karo aur relevant chunks return karo.

    Returns:
        (chunks: list[str], is_relevant: bool)
        - chunks     : relevant text chunks (khali list agar nahi mila)
        - is_relevant: True agar data relevant threshold ke andar hai
    """
    query_embedding = create_embedding_query(query)
    chunks, min_dist = load_faiss_index(query_embedding, k=5)

    relevant = is_relevant(min_dist)

    print(f"🔍 RAG search — min distance: {min_dist:.4f} | relevant: {relevant}")
    return chunks, relevant