"""
searchquerydb.py — FAISS mein query karo aur decide karo ki naya web search chahiye ya nahi.
"""

from vector_and_Ragservice.RAG_index import ask_query


def search_in_db(query: str):
    """
    Pehle FAISS/RAG mein search karo.

    Returns:
        (context_chunks: list[str], needs_web_search: bool)
    """
    chunks, relevant = ask_query(query)

    if relevant and chunks:
        print("✅ RAG mein relevant data mila — web search skip.")
        return chunks, False
    else:
        print("🌐 RAG mein relevant data nahi mila — web search zaroori hai.")
        return [], True
