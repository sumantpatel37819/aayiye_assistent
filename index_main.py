"""
index_main.py — Aayie Personal Assistant ka main entry point (Restored Intent-Classifier Version).
"""

import asyncio
import os
import sys

# Windows terminal UTF-8 print fix
if sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from Query_process.continue_chat import (
    ChatSession,
    is_clear_command,
    is_exit_command,
    is_history_command,
)
from Query_process.query_index import handle_query
from agent.router import classify_intent
from agent.code_generator import generate_code
from agent.safe_executor import execute_code
from agent.tools.weather_tool import get_weather
from agent.tools.sheets_tool import execute_sheets_instruction

# ─────────────────────────────────────────────
# Working directory (jahan se script chal rahi hai)
# ─────────────────────────────────────────────
WORKSPACE_DIR = os.path.dirname(os.path.abspath(__file__))

# ─────────────────────────────────────────────
# Display helpers
# ─────────────────────────────────────────────

DIVIDER = "=" * 55

def print_header():
    print(f"\n{DIVIDER}")
    print("    🤖  Aayie — Your AI Personal Assistant (Intent-Router Mode) 🤖")
    print(f"{DIVIDER}")
    print("  I can:")
    print("    • Kisi bhi topic pe search karke answer de sakta hoon")
    print("    • Files read/write/edit kar sakta hoon (JSON, Excel, CSV...)")
    print("    • Applications open kar sakta hoon")
    print("    • Folders/files manage kar sakta hoon")
    print()
    print("  Commands:")
    print("    exit / q      → band karo")
    print("    clear / reset → chat history saaf karo")
    print("    history       → purani baatein dekho")
    print(f"{DIVIDER}\n")


def print_answer(result: dict):
    source_label = "🌐 Web Search" if result["source"] == "web" else "🌐 Web Search"
    print(f"\n{DIVIDER}")
    print(f"  {source_label}")
    print(DIVIDER)
    print(result["answer"])

    if result.get("images"):
        print(f"\n📷 Images ({len(result['images'])} mili):")
        for i, img in enumerate(result["images"][:5], 1):
            print(f"  {i}. {img}")

    print(DIVIDER)

# ─────────────────────────────────────────────
# CHAT intent handler (no web search, pure LLM)
# ─────────────────────────────────────────────

_current_web_context = ""

def handle_chat(query: str, history_str: str) -> str:
    """Simple conversation — LLM directly answers in English."""
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_ollama.llms import OllamaLLM
    
    global _current_web_context
    context_injection = ""
    if _current_web_context:
        context_injection = f"\n\nUse the following web context if relevant to the user's question:\n{_current_web_context}\n\n"

    model = OllamaLLM(model="llama3.2", keep_alive=-1)
    template = """You are a friendly and helpful AI personal assistant named Aayie.
Answer the user's message conversationally. Keep it concise and warm.
IMPORTANT: Always respond in English only, regardless of what language the user writes in.
If the user asks what you can do, mention: web search, weather, Google Sheets, opening apps, file management.
{context_injection}
{history}
User: {query}
Aayie:"""
    prompt = ChatPromptTemplate.from_template(template)
    chain = prompt | model
    return chain.invoke({"history": history_str, "query": query, "context_injection": context_injection}).strip()


def extract_enrich_params(query: str) -> tuple[str, str | None]:
    """Extract State and City (optional) from an ENRICH_SHEET query."""
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_ollama.llms import OllamaLLM
    import json
    import re

    model = OllamaLLM(model="llama3.2", keep_alive=-1)
    prompt = ChatPromptTemplate.from_template(
        'Extract the state and city (if explicitly mentioned) from this query for a travel database. '
        'Return ONLY raw JSON with no markdown formatting, no backticks, and no explanation. '
        'Must have keys "state" and "city". '
        'CRITICAL: If the user asks for all places in a state (e.g. "saare places", "all places") or does NOT name a specific city, you MUST set city to "all". '
        'If a specific city is mentioned (e.g. "gaya", "patna"), set city to that exact name.\n'
        'Query: "{query}"\nJSON:'
    )
    try:
        res = (prompt | model).invoke({"query": query}).strip()
        
        # Clean markdown code blocks if any (fallback)
        if "```json" in res:
            res = res.split("```json")[1].split("```")[0].strip()
        elif "```" in res:
            res = res.split("```")[1].split("```")[0].strip()
            
        # Try to find a JSON object using regex if there's surrounding text
        match = re.search(r'\{.*\}', res, re.DOTALL)
        if match:
            res = match.group(0)
            
        data = json.loads(res)
        state = data.get("state")
        city = data.get("city")
        if isinstance(city, str) and city.lower() in ["null", "none", "", "n/a", "all", "any"]:
            city = None
        return state, city
    except Exception as e:
        print(f"Error extracting params: {e}")
        # Very simple fallback using string matching if LLM fails
        query_lower = query.lower()
        if "bihar" in query_lower: return "Bihar", "Nalanda" if "nalanda" in query_lower else ("Kaimur" if "kaimur" in query_lower else None)
        if "goa" in query_lower: return "Goa", None
        if "rajasthan" in query_lower: return "Rajasthan", None
        if "nepal" in query_lower: return "Nepal", None
        if "bhutan" in query_lower: return "Bhutan", None
        return None, None


# ─────────────────────────────────────────────
# Main chat loop
# ─────────────────────────────────────────────

async def main():
    print_header()
    session = ChatSession()

    while True:
        try:
            user_input = input("\n🧑 Aap: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\nAlvida! 👋")
            break

        if not user_input:
            print("  ⚠ Khali input — kuch toh likhein.")
            continue

        # Special commands
        if is_exit_command(user_input):
            print("\nAlvida! Aayie ka shukriya. 👋")
            break

        if is_clear_command(user_input):
            session.clear()
            continue

        if is_history_command(user_input):
            session.print_history()
            continue

        # Build history string for context
        history_str = ""
        for msg in session.get_history()[-6:]:
            role = "Aap" if msg["role"] == "user" else "Aayie"
            history_str += f"{role}: {msg['content']}\n"

        # ── Step 1: Router — intent classify ─────────────────────
        print(f"\n🔍 Intent classify ho raha hai...")
        lower_input = user_input.lower()
        if "json" in lower_input and ("update" in lower_input or "sync" in lower_input or "karo" in lower_input or "check" in lower_input or "file" in lower_input):
            intent = "SYNC_JSON"
        else:
            intent = classify_intent(user_input)
        print(f"  📌 Intent: {intent}")

        session.add_user(user_input)

        # ── Step 2: Dispatch based on intent ─────────────────────
        try:
            if intent == "CHAT":
                # Simple conversation — no search, pure LLM
                print("\n💬 Direct jawab de raha hoon...")
                answer = handle_chat(user_input, history_str)
                print(f"\n{DIVIDER}")
                print("  💬 Aayie")
                print(DIVIDER)
                print(answer)
                print(DIVIDER)
                session.add_assistant(answer)

            elif intent == "WEB_SEARCH":
                print("  🌐 Web Search chal raha hai (Context Injection Mode)...")
                # Call async handle_query safely
                result = await handle_query(user_input, session.get_history())
                print_answer(result)
                session.add_assistant(result["answer"])
                
                # Save context for future follow-up chats
                global _current_web_context
                if isinstance(result.get("context"), list):
                    _current_web_context = "\n".join(result["context"])
                else:
                    _current_web_context = str(result.get("context", ""))

            elif intent == "WEATHER":
                # Extract location from user input using LLM
                print("\n🌤 Weather fetch ho raha hai...")
                from langchain_core.prompts import ChatPromptTemplate
                from langchain_ollama.llms import OllamaLLM
                _loc_model = OllamaLLM(model="llama3.2", keep_alive=-1)
                loc_prompt = ChatPromptTemplate.from_template(
                    "Extract ONLY the city/location name from this query. Reply with just the location name, nothing else.\n\nQuery: {q}\n\nLocation:"
                )
                location = (loc_prompt | _loc_model).invoke({"q": user_input}).strip()
                print(f"  📍 Location: {location}")
                weather_result = get_weather(location)
                print(f"\n{DIVIDER}")
                print("  🌤 Weather")
                print(DIVIDER)
                print(weather_result)
                print(DIVIDER)
                session.add_assistant(f"Weather info fetched for {location}.")

            elif intent == "GOOGLE_SHEETS":
                print("\n  📊 Google Sheets operation chal raha hai...")
                from agent.tools.sheets_tool import execute_sheets_instruction
                sheet_result = execute_sheets_instruction(user_input)
                print(f"\n{DIVIDER}")
                print("  📊 Sheets Result")
                print(DIVIDER)
                print(sheet_result)
                print(DIVIDER)
                session.add_assistant("Executed sheets operation.")
            
            elif intent == "ENRICH_SHEET":
                print("\n  📝 Sheet Enrichment pipeline chal raha hai...")
                state, city = extract_enrich_params(user_input)
                if not state:
                    print("Could not understand which state you want to process. Please specify a state (e.g., 'Bihar ke places sheet me daalo').")
                    continue
                
                print(f"  State: {state}, City Filter: {city if city else 'All'}")
                from agent.tools.sheet_enricher_tool import enrich_state_places
                from agent.tools.sheets_tool import write_enriched_rows_to_sheet
                
                try:
                    # Pass the arguments cleanly whether it's tool-wrapped or not
                    if hasattr(enrich_state_places, "invoke"):
                        result_msg = enrich_state_places.invoke({"state_name": state, "city_name": city})
                    else:
                        result_msg = enrich_state_places(state_name=state, city_name=city)
                    
                    print(f"\n{DIVIDER}")
                    print("  📝 Enrich Result")
                    print(DIVIDER)
                    print(result_msg)
                    print(DIVIDER)
                    session.add_assistant("Enriched places and added to sheet.")
                except Exception as e:
                    print(f"Error during sheet enrichment: {e}")

            elif intent == "REPAIR_SHEET":
                print("\n  🛠 Sheet Repair pipeline chal raha hai...")
                state, _ = extract_enrich_params(user_input)
                if not state:
                    print("Could not understand which state you want to repair. Please specify a state (e.g., 'Bihar ke places repair karo').")
                    continue
                
                print(f"  State: {state}")
                from agent.tools.sheet_repair_tool import repair_state_places
                
                try:
                    result_msg = repair_state_places(state_name=state)
                    
                    print(f"\n{DIVIDER}")
                    print("  🛠 Repair Result")
                    print(DIVIDER)
                    print(result_msg)
                    print(DIVIDER)
                    session.add_assistant("Scanned and repaired missing data in the sheet.")
                except Exception as e:
                    print(f"Error during sheet repair: {e}")

            elif intent == "SYNC_JSON":
                print("\n  🔄 JSON files synchronising & updating...")
                from agent.tools.json_sync_tool import run_json_sync
                try:
                    result_msg = run_json_sync()
                    print(f"\n{DIVIDER}")
                    print("  🔄 JSON Sync Result")
                    print(DIVIDER)
                    print(result_msg)
                    print(DIVIDER)
                    session.add_assistant("Synchronised and updated all Places_db JSON files from source.")
                except Exception as e:
                    print(f"Error during JSON sync: {e}")

            elif intent == "SYSTEM_ACTION":
                print(f"\n🤖 System action chal raha hai: {user_input}")
                code = generate_code(task=user_input, cwd=WORKSPACE_DIR)
                if code:
                    print(f"\n{DIVIDER}\n📝 Generated Code:\n{DIVIDER}\n{code}\n{DIVIDER}")
                    confirm = input("\n▶ Ye code chalayein? (y/n): ").strip().lower()
                    if confirm == 'y':
                        print("\n  ⚙ Code execute ho raha hai...")
                        output = execute_code(code=code, cwd=WORKSPACE_DIR, auto_approve=True)
                        print(f"\n{DIVIDER}\n  ✅ Output:\n{DIVIDER}\n{output}\n{DIVIDER}")
                        session.add_assistant("Executed a system script successfully.")
                    else:
                        print("  ❌ Execution cancelled.")
                else:
                    print("  ❌ Code generate nahi ho paya.")

        except Exception as e:
            print(f"\n❌ Error aaya: {e}")
            print("   Dobara try karein ya query badlein.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1].lower() in ["--cli", "-c", "cli"]:
        print("🖥️ Starting Aayie in Terminal CLI mode...")
        asyncio.run(main())
    else:
        print("🎨 Launching Aayie Graphical User Interface (GUI)...")
        from gui_main import AayieGUI
        app = AayieGUI()
        app.mainloop()

