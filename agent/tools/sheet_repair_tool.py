"""
agent/tools/sheet_repair_tool.py

This tool scans the spreadsheet for a given state, looks for empty fields or 
fields containing negative LLM responses (e.g. "unfortunately, I don't have enough..."),
and repairs them by running a live Google search (attempting Google login) 
to extract Gemini AI overview + web links, then rewriting the field.
"""

import time
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama.llms import OllamaLLM

from agent.tools.sheets_tool import get_existing_places_from_sheet, update_enriched_row_in_sheet
from agent.tools.sheet_enricher_tool import CSV_COLUMNS, _rewrite
from gettinglinks.google_login_search import search_and_extract_gemini_and_links, close_login_driver

NEGATIVE_PHRASES = [
    "unfortunately, i don't have enough",
    "unfortunately, i don't have",
    "i couldn't find any specific",
    "no specific local food details available",
    "no information",
    "does not provide",
    "not mentioned",
    "distance from capital not found",
    "i don't have any specific"
]

def needs_repair(text: str) -> bool:
    """Check if the cell content is missing or has a negative LLM response."""
    if not text or not text.strip():
        return True
    
    text_lower = text.lower()
    for phrase in NEGATIVE_PHRASES:
        if phrase in text_lower:
            return True
    return False

def repair_state_places(state_name: str, city_name: str | None = None) -> str:
    """Scans and repairs missing/negative data in the state's Google Sheet.
    
    Args:
        state_name: State jiska data repair karna hai (e.g., "Bihar").
        city_name: Agar sirf ek city ka data repair karna ho (e.g., "Patna").
                   None ya falsy value hone par poore state ka data repair hoga.
    """
    
    from agent.task_controller import task_controller

    city_filter = city_name.strip().lower() if city_name else None

    if city_filter:
        print(f"\n🔍 [Sheet Repair] Starting scan for state: {state_name}, city: {city_name}")
    else:
        print(f"\n🔍 [Sheet Repair] Starting scan for state: {state_name} (all cities)")
    
    existing_places = get_existing_places_from_sheet(state_name.title())
    
    if not existing_places:
        return f"No existing places found in the sheet for {state_name}."

    task_controller.reset(f"Repairing {state_name}" + (f" ({city_name})" if city_filter else ""), len(existing_places))

    fields_to_check = {
        "Description": "tourist description and importance",
        "Recognition": "official recognition and significance",
        "culture": "local culture and traditions",
        "Address_from_Capital": "distance and route from state capital",
        "means_of_transport": "how to reach by train, bus, road",
        "Famous_Dish": "famous local food and dishes",
        "History": "historical significance and background"
    }
    
    repaired_count = 0
    total_count = len(existing_places)
    
    try:
        # existing_places is a dict: { "place_name_lower": { "row_index": X, "data": [...] } }
        processed_rows = set()
        for idx, (place_lower, info) in enumerate(existing_places.items(), start=1):
            row_idx = info["row_index"]
            if row_idx in processed_rows:
                continue
            processed_rows.add(row_idx)

            row_data = info["data"]
            
            # Reconstruct the row dict for easier manipulation
            row_dict = {}
            for i, col in enumerate(CSV_COLUMNS):
                row_dict[col] = row_data[i].strip() if i < len(row_data) else ""
            
            pname = row_dict.get("famous_place_name") or row_dict.get("Place") or place_lower.title()

            # ── City filter ───────────────────────────────────
            if city_filter:
                row_city = (row_dict.get("district") or row_dict.get("Place") or row_dict.get("City") or "").strip().lower()
                if not (city_filter in row_city or (row_city and row_city in city_filter)):
                    continue  # Is place ka city match nahi kiya — skip karo
            # ─────────────────────────────────────────────────
            if not task_controller.check_point(idx, total_count, pname, f"Repairing {state_name}"):
                print("  ⏹ Repair task stopped by user.")
                break
            
            needs_update = False
            
            # Check each field
            for field, query_context in fields_to_check.items():
                cell_value = row_dict.get(field, "")
                
                if needs_repair(cell_value):
                    print(f"\n  🛠 Repairing [{field}] for '{pname}'...")
                    print(f"    Current value: '{cell_value[:50]}...'")
                    
                    # 1. Search Google with Gemini
                    query = f"{pname} {state_name} {query_context}"
                    print(f"    🔍 Searching: '{query}'")
                    raw_extracted_text = search_and_extract_gemini_and_links(query, num_results=2)
                    
                    # 2. Rewrite
                    if raw_extracted_text:
                        # Assuming the _rewrite from enricher handles prompts based on field name, but lowercase it
                        prompt_field_map = {
                            "Description": "description",
                            "Recognition": "recognition",
                            "culture": "culture",
                            "Address_from_Capital": "address",
                            "means_of_transport": "transport",
                            "Famous_Dish": "food",
                            "History": "history"
                        }
                        
                        rewrite_field = prompt_field_map.get(field, "description")
                        new_text = _rewrite(rewrite_field, raw_extracted_text, pname, state_name)
                        
                        if new_text and not needs_repair(new_text):
                            print(f"    ✅ Repaired [{field}] -> {len(new_text)} chars")
                            row_dict[field] = new_text
                            needs_update = True
                        else:
                            print(f"    ⚠ LLM could not repair the text properly.")
                    else:
                        print(f"    ⚠ No text extracted from Google for '{pname}'.")
            
            if needs_update:
                # Update sheet
                flat_row = [row_dict.get(col, "") for col in CSV_COLUMNS]
                # Ensure ID is preserved
                flat_row[0] = row_data[0] if row_data else ""
                
                print(f"  ⬆ Updating Google Sheet row {row_idx} for '{pname}'...")
                res_msg = update_enriched_row_in_sheet(state_name.title(), row_idx, flat_row)
                print(f"  ✅ {res_msg}")
                repaired_count += 1
                
                # Sleep briefly to avoid Google Sheets API rate limits
                time.sleep(1.5)
                
    except Exception as e:
        print(f"\n❌ Error during repair process: {e}")
    finally:
        print("🛑 Closing browser (if open)...")
        close_login_driver()
        
    return f"Repair process completed for {state_name}. Updated {repaired_count} rows."

if __name__ == "__main__":
    # Test run
    # res = repair_state_places("Bihar")
    # print(res)
    pass
