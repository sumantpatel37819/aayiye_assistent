"""
query_index.py — ek query ka complete lifecycle handle karta hai:
  1. RAG/FAISS mein check karo
  2. Agar nahi mila → web search + scrape + RAG mein store
  3. LLM se answer generate karo
  4. (context, answer, images) return karo
"""

import asyncio

import asyncio
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool

# pyrefly: ignore [missing-import]
from langchain_ollama.llms import OllamaLLM

from Query_process.searchquerydb import search_in_db
from scraping_web.index import run_query
# FAISS/RAG imports removed

# ─────────────────────────────────────────────
# LLM setup
# ─────────────────────────────────────────────

_model = OllamaLLM(model="llama3.2", keep_alive=-1)

_template = """You are a knowledgeable and friendly travel guide and personal assistant named Aayie.
Answer questions using the provided context from web search results.

Rules:
- ALWAYS respond in English only.
- Answer based on the provided context below.
- Include how to reach the place, best time to visit, and safety tips where relevant.
- If the context is not sufficient, say "I need more information about this topic."
- Keep the tone warm and conversational.

Context (from web):
{context}

User Question:
{query}

Answer:
"""

_prompt = ChatPromptTemplate.from_template(_template)
_chain  = _prompt | _model


_rewrite_template = """
Given the following chat history and a new user query, rephrase the new query to be a standalone search query that contains all necessary context from the chat history.
If the new query is already standalone and clear, return it as is. Do NOT answer the question, ONLY return the standalone search query.

Chat History:
{chat_history}

New User Query: {query}

Standalone Search Query:
"""
_rewrite_prompt = ChatPromptTemplate.from_template(_rewrite_template)
_rewrite_chain = _rewrite_prompt | _model


# --- Text Refiner Chain (For Selenium Extracted Raw Text) ---
_refine_template = """
You are a helpful data extraction assistant.
Below is raw text extracted from a webpage. It contains noise like ads, navigation menus, and footers.
Your task is to extract and summarize ONLY the useful information that is relevant to the user's query: "{query}".
If the text contains nothing relevant, reply with exactly: "NO_RELEVANT_DATA".
Keep the summary informative and detailed, preserving key facts, places, instructions, or numbers.

Raw Text:
{text}

Clean Information:
"""
_refine_prompt = ChatPromptTemplate.from_template(_refine_template)
_refine_chain = _refine_prompt | _model


async def refine_extracted_text(raw_text: str, query: str) -> str:
    """
    Kachra text ko LLM ke through clean karta hai.
    """
    # LLM context window bachaane ke liye text truncate karo (10000 characters)
    clean_raw = "\n".join(line.strip() for line in raw_text.splitlines() if line.strip())
    truncated_text = clean_raw[:10000]

    print(f"    🧹 Refining text with llama3.2 (Length: {len(truncated_text)})...")
    try:
        refined = await _refine_chain.ainvoke({
            "query": query,
            "text": truncated_text
        })
        refined = refined.strip()
        if "NO_RELEVANT_DATA" in refined:
            return ""
        return refined
    except Exception as e:
        print(f"    ❌ Refine error: {e}")
        return clean_raw[:2000]  # Fallback: return top 2000 chars


# ─────────────────────────────────────────────
# Main handler
# ─────────────────────────────────────────────

async def handle_query(query: str, chat_history: list = None):
    """
    Ek query process karo — RAG first, phir web search agar zaroori ho.
    """
    images = []
    source = "rag"

    # Chat history formatting for context and rewriting
    history_str = ""
    if chat_history:
        for msg in chat_history[-6:]:  # Last 3 exchanges
            role = "User" if msg["role"] == "user" else "Raja"
            history_str += f"{role}: {msg['content']}\n"

    # ── Step 1: Context-Aware Query Reformulation ───
    search_query = query
    if history_str.strip():
        print(f"\n🧠 Query rewrite ho rahi hai (Chat history ke basis pe)...")
        rewritten = _rewrite_chain.invoke({
            "chat_history": history_str,
            "query": query
        })
        search_query = rewritten.strip()
        print(f"  📝 New Standalone Query: '{search_query}'")

    # ── Step 2: Web Search Directly (Bypassing FAISS) ──
    source = "web"
    print(f"\n🌐 Web search chal rahi hai: '{search_query}'")

    scrape_results = await run_query(search_query)

    if not scrape_results:
        return {
            "answer" : "Mujhe is query ke liye koi information nahi mili. Kripya query badlo.",
            "context": [],
            "images" : [],
            "source" : "web"
        }

    extracted_texts = []
    for item in scrape_results:
        if item and item[0]:
            raw_txt = item[0]
            refined_txt = await refine_extracted_text(raw_txt, search_query)
            if refined_txt:
                extracted_texts.append(refined_txt)
        if item and item[1]:
            images.extend(item[1])

    if not extracted_texts:
        return {
            "answer" : "Mujhe is query ke liye search me koi useful information nahi mili. Kripya dusra sawal puchiye.",
            "context": [],
            "images" : images,
            "source" : "web"
        }

    context_chunks = extracted_texts

    # ── Step 3: LLM se answer ─────────────────
    context_str = "\n\n---\n\n".join(context_chunks) if context_chunks else "No context available."

    # Chat history ko context mein jodna (agar diya gaya hai)
    history_str = ""
    if chat_history:
        for msg in chat_history[-6:]:  # Last 3 exchanges
            role = "User" if msg["role"] == "user" else "Raja"
            history_str += f"{role}: {msg['content']}\n"

    final_context = f"{history_str}\n\n{context_str}" if history_str else context_str

    print("\n🤖 LLM answer generate ho raha hai...")
    answer = _chain.invoke({
        "context": final_context,
        "query"  : query
    })

    return {
        "answer" : answer,
        "context": context_chunks,
        "images" : images,
        "source" : source
    }

@tool
def handle_web_search(query: str) -> str:
    """Searches the internet for up-to-date information to answer the user's question. Use this when the user asks about general knowledge, current events, or something outside of the pre-loaded data.
    
    Args:
        query (str): The search query to look up on the web.
    """
    import asyncio
    import threading
    
    result_container = []
    
    def _run_in_thread():
        # Create a new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            res = loop.run_until_complete(handle_query(query, []))
            result_container.append(res)
        finally:
            loop.close()
            
    t = threading.Thread(target=_run_in_thread)
    t.start()
    t.join()
    
    if not result_container:
        return "Search failed due to an internal error."
        
    res = result_container[0]
    
    # Save context globally so future generic chats know about it
    from index_main import _current_web_context
    import index_main
    if isinstance(res.get("context"), list):
        index_main._current_web_context = "\n".join(res["context"])
    else:
        index_main._current_web_context = str(res.get("context", ""))
        
    return res["answer"]
