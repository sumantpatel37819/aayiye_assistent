"""
agent/services/tour_rag_service.py

Dedicated Tour RAG Service for Aayie Chatbot testing:
Retrieves semantic vectors from Pinecone (Index: 'sonukumar') embedded via 'mxbai-embed-large'
and generates grounded, accurate travel advice using Ollama Llama 3.2.
"""

import os
from dotenv import load_dotenv
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama.llms import OllamaLLM

from agent.tools.pinecone_sync_tool import get_pinecone_index, get_embedding

load_dotenv()

_llm = OllamaLLM(model="llama3.2", keep_alive=-1)

_RAG_PROMPT = ChatPromptTemplate.from_template(
    """You are TourKaro AI — an intelligent, highly knowledgeable Indian Travel & Tourism Assistant.
Answer the user's travel question accurately, warmly, and conversationally using ONLY the verified tourist destination facts provided in the context below.

Rules:
1. Always state specific details when asked: exact operating timings, entry fee/ticket costs, ideal visiting hours (morning/sunset), and whether the place suits couples, families, or devotees.
2. If the user asks for recommendations, highlight the top matching destinations from the context and explain why they fit the user's criteria.
3. Keep the tone engaging, helpful, and concise.

Verified Tourist Places Context:
{context}

User Question:
{question}

TourKaro AI Answer:"""
)


def query_tour_rag(query: str, top_k: int = 4, filter_city: str = None) -> dict:
    """
    1. Embed query with mxbai-embed-large
    2. Query Pinecone serverless index
    3. Synthesize grounded answer with Ollama Llama 3.2
    Returns: { "answer": str, "sources": list[dict] }
    """
    try:
        index = get_pinecone_index()
        query_vector = get_embedding(query, is_query=True)

        query_filter = None
        if filter_city:
            query_filter = {"city": {"$eq": filter_city.strip().title()}}

        search_res = index.query(
            vector=query_vector,
            top_k=top_k,
            include_metadata=True,
            filter=query_filter
        )

        matches = search_res.get("matches", [])
        if not matches:
            return {
                "answer": "Pinecone me is query se match hone wale places nahi mile. Kripya pehle CSV data ko Pinecone me sync karein ya query badal kar dekhein.",
                "sources": []
            }

        context_parts = []
        sources = []

        for m in matches:
            meta = m.get("metadata", {})
            score = round(m.get("score", 0.0), 3)
            place_text = meta.get("text", "")

            context_parts.append(f"--- Place (Match Score: {score}) ---\n{place_text}\n---")
            sources.append({
                "name": meta.get("name", "Unknown"),
                "city": meta.get("city", ""),
                "state": meta.get("state", ""),
                "category": meta.get("category", ""),
                "opening_hour": meta.get("opening_hour", ""),
                "entry_fee": meta.get("entry_fee", ""),
                "score": score
            })

        combined_context = "\n\n".join(context_parts)

        chain = _RAG_PROMPT | _llm
        raw_answer = chain.invoke({
            "context": combined_context,
            "question": query
        }).strip()

        return {
            "answer": raw_answer,
            "sources": sources
        }

    except Exception as e:
        print(f"❌ Tour RAG Service error: {e}")
        return {
            "answer": f"Tour RAG query failed: {e}",
            "sources": []
        }


def format_rag_response_for_chat(result: dict) -> str:
    """Formats answer + retrieved sources into a clean markdown card for GUI/CLI chat."""
    ans = result.get("answer", "")
    sources = result.get("sources", [])

    if not sources:
        return ans

    cards = []
    for s in sources:
        timing = f" | ⏰ {s['opening_hour']}" if s.get('opening_hour') else ""
        fee = f" | 🎟 {s['entry_fee']}" if s.get('entry_fee') else ""
        cards.append(f"  • **{s['name']}** ({s['city']}, {s['state']}) — *{s['category']}* [Match: {int(s['score']*100)}%]{timing}{fee}")

    sources_block = "\n".join(cards)
    return f"{ans}\n\n📌 **Verified Places Retrieved from Pinecone:**\n{sources_block}"
