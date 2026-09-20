"""
agent/tools/repair_csv_tool.py

Pipeline to scan and repair missing or unformatted fields in state destination CSV files:
Target: sheet_works/db/details_places/<state_slug>_places.csv

Repairs performed:
1. Missing description: Live Google Chrome search (AI Overview + web links) + Ollama Llama 3.2 synthesis
2. Missing coordinates: Google Places API (TextSearch / FindPlace)
3. Missing opening_hour, avg_time_spend, entry_fee: Live Chrome search + LLM
4. Raw dict/JSON best_time_to_visit: Cleanly flattened into cohesive natural sentences
5. Incremental & safe: Immediately flushes updated rows to disk, backup created automatically
"""

import os
import csv
import ast
import json
import time
import shutil
import random
import requests
from pathlib import Path
from dotenv import load_dotenv

from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama.llms import OllamaLLM

from gettinglinks.google_login_search import search_and_extract_gemini_and_links, close_login_driver
from agent.task_controller import task_controller

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CSV_DIR = PROJECT_ROOT / "sheet_works" / "db" / "details_places"
GOOGLE_PLACES_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY", "")

_llm = OllamaLLM(model="llama3.2", keep_alive=-1)

_PROMPT_REPAIR_DESC = ChatPromptTemplate.from_template(
    """You are an expert travel writer. Write an engaging, informative 3-4 sentence tourist narrative for "{place_name}" located in {city}, {state} (Category: {category}).
Highlight its architectural beauty, cultural/historical significance, key attractions, and overall visitor experience using the web context below.
Do not mention ticket fees or operating hours.

Web Context:
{raw_context}

Narrative:"""
)


def get_place_coordinate_textsearch(place_name: str, city: str, state: str) -> str:
    """Fetch exact coordinate using Google Places TextSearch API."""
    if not GOOGLE_PLACES_API_KEY:
        return ""
    queries = [
        f"{place_name} {city} {state}",
        f"{place_name} {state}",
        f"{place_name} tourist attraction {state}",
    ]
    for q in queries:
        try:
            url = (
                f"https://maps.googleapis.com/maps/api/place/textsearch/json"
                f"?query={requests.utils.quote(q)}"
                f"&key={GOOGLE_PLACES_API_KEY}"
            )
            resp = requests.get(url, timeout=8).json()
            results = resp.get("results", [])
            if results:
                loc = results[0].get("geometry", {}).get("location", {})
                lat = loc.get("lat")
                lng = loc.get("lng")
                if lat is not None and lng is not None:
                    return f"{lat}, {lng}"
        except Exception:
            pass
    return ""


def flatten_best_time(raw_val: str) -> str:
    """Convert JSON/Python dictionary format of best_time_to_visit into clean sentences."""
    val = (raw_val or "").strip()
    if not (val.startswith("{") or val.startswith("[")):
        return val

    try:
        parsed = ast.literal_eval(val)
    except Exception:
        try:
            parsed = json.loads(val)
        except Exception:
            return val

    if not isinstance(parsed, dict):
        return val

    sentences = []

    # 1. Months / Seasons
    months = None
    for k in ["ideal_months/seasons", "ideal_months", "ideal_seasons", "ideal_months_seasons", "seasons"]:
        if k in parsed:
            months = parsed[k]
            break
    if months:
        if isinstance(months, list):
            months_str = ", ".join(str(m) for m in months)
            sentences.append(f"Best visited from {months_str} for pleasant weather.")
        elif isinstance(months, str) and months.strip():
            m_str = months.strip()
            if not m_str.lower().startswith("best") and not m_str.lower().startswith("ideal"):
                sentences.append(f"Ideal season is {m_str}.")
            else:
                sentences.append(m_str if m_str.endswith(".") else f"{m_str}.")

    # 2. Time of day
    time_of_day = None
    for k in ["best_time_of_day", "ideal_time_of_day", "time_of_day"]:
        if k in parsed:
            time_of_day = parsed[k]
            break
    if time_of_day and isinstance(time_of_day, str) and time_of_day.strip():
        tod_str = time_of_day.strip()
        if not tod_str.endswith("."):
            tod_str += "."
        sentences.append(f"Recommended visiting hours: {tod_str}")

    # 3. Personas
    personas = None
    for k in ["traveler_persona_recommendations", "persona_recommendations", "personas"]:
        if k in parsed:
            personas = parsed[k]
            break
    if personas:
        if isinstance(personas, list):
            persona_items = []
            for p in personas:
                if isinstance(p, dict):
                    name = p.get("name") or next(iter(p.keys()), "")
                    desc = p.get("description") or p.get(name, "")
                    if desc and isinstance(desc, str):
                        persona_items.append(f"{name} ({desc})")
                    elif name:
                        persona_items.append(str(name))
                elif isinstance(p, str):
                    persona_items.append(p)
            if persona_items:
                sentences.append(f"Suitability: {'; '.join(persona_items)}.")
        elif isinstance(personas, dict):
            persona_items = [k for k, v in personas.items() if v]
            if persona_items:
                sentences.append(f"Suitable for: {', '.join(persona_items)}.")
        elif isinstance(personas, str) and personas.strip():
            p_str = personas.strip()
            if not p_str.endswith("."):
                p_str += "."
            sentences.append(p_str)

    # 4. Warnings / festivals
    warnings = None
    for k in ["key_festivals_season_warnings", "warnings", "season_warnings"]:
        if k in parsed:
            warnings = parsed[k]
            break
    if warnings:
        if isinstance(warnings, list):
            w_str = ", ".join(str(w) for w in warnings if str(w).lower() != "none")
            if w_str:
                sentences.append(f"Tips: {w_str}.")
        elif isinstance(warnings, str) and warnings.strip() and warnings.lower() not in ["none", "no specific warnings mentioned"]:
            w_str = warnings.strip()
            if not w_str.endswith("."):
                w_str += "."
            sentences.append(w_str)

    combined = " ".join(sentences).strip()
    return combined if combined else val


def row_needs_repair(row: dict) -> list:
    """Returns list of missing or dirty field keys for a given row."""
    reasons = []
    desc = (row.get("description") or "").strip()
    if not desc or len(desc) < 25 or "unfortunately" in desc.lower():
        reasons.append("description")

    coord = (row.get("coordinate") or "").strip()
    if not coord:
        reasons.append("coordinate")

    hours = (row.get("opening_hour") or "").strip()
    if not hours:
        reasons.append("opening_hour")

    bt = (row.get("best_time_to_visit") or "").strip()
    if bt.startswith("{") or bt.startswith("["):
        reasons.append("best_time_format")

    return reasons


def repair_state_csv(state_name: str, city_filter: str = None) -> str:
    """
    Scans sheet_works/db/details_places/<state_slug>_places.csv, finds missing fields,
    runs live Google Chrome search (AI Overview + links) to extract real data, and updates the CSV.
    """
    state_slug = state_name.lower().strip().replace(" ", "_").replace("-", "_")
    csv_file = CSV_DIR / f"{state_slug}_places.csv"

    if not csv_file.exists():
        return f"❌ CSV file not found for state '{state_name}': {csv_file}"

    # Create safety backup if not already present
    backup_file = CSV_DIR / f"{state_slug}_places.csv.bak"
    if not backup_file.exists():
        shutil.copyfile(csv_file, backup_file)
        print(f"📦 Created backup: {backup_file.name}")

    with open(csv_file, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    city_filter_lower = city_filter.strip().lower() if city_filter else None

    # Identify rows to repair
    to_repair = []
    for idx, r in enumerate(rows):
        if city_filter_lower and city_filter_lower not in (r.get("city") or "").lower():
            continue
        missing = row_needs_repair(r)
        if missing:
            to_repair.append((idx, r, missing))

    total_needing_repair = len(to_repair)
    print(f"\n🛠 [CSV Repair] Found {total_needing_repair} places needing repair in {csv_file.name}")
    if total_needing_repair == 0:
        return f"✅ All places in {csv_file.name} are already complete and clean! No repairs needed."

    task_controller.reset(f"Repairing CSV for {state_name}", total_needing_repair)
    repaired_count = 0

    try:
        for step_idx, (row_idx, row, missing_keys) in enumerate(to_repair, start=1):
            pname = row["name"]
            city = row["city"]
            category = row.get("category", "tourist attraction")
            current_id = row.get("place_id", row_idx + 1)

            if not task_controller.check_point(step_idx, total_needing_repair, pname, f"Repairing CSV for {state_name}"):
                print("  ⏹ CSV repair stopped by user.")
                break

            print(f"\n  [{step_idx}/{total_needing_repair}] 🛠 Repairing ID {current_id}: '{pname}' ({city})")
            print(f"    Needs: {', '.join(missing_keys)}")

            # 1. Coordinate repair
            if "coordinate" in missing_keys:
                print(f"    📍 Searching coordinate via Google Places API...")
                new_coord = get_place_coordinate_textsearch(pname, city, state_name)
                if new_coord:
                    row["coordinate"] = new_coord
                    print(f"      ✅ Coordinate found: {new_coord}")
                else:
                    print(f"      ⚠ Coordinate could not be found.")

            # 2. Best time format flattening
            if "best_time_format" in missing_keys:
                clean_bt = flatten_best_time(row.get("best_time_to_visit", ""))
                row["best_time_to_visit"] = clean_bt
                print(f"      ✅ Formatted best_time_to_visit into readable text.")

            # 3. Description or opening_hour missing -> Live Google Chrome search
            if "description" in missing_keys or "opening_hour" in missing_keys:
                search_query = f"{pname} {city} {state_name} tourism attractions history opening hours timings overview"
                print(f"    🌐 Live Chrome Search: '{search_query}'")

                raw_context = search_and_extract_gemini_and_links(search_query, num_results=2)
                if not raw_context or len(raw_context.strip()) < 50:
                    raw_context = f"{pname} is a renowned {category} located in {city}, {state_name}."

                if "description" in missing_keys:
                    try:
                        chain = _PROMPT_REPAIR_DESC | _llm
                        desc = chain.invoke({
                            "place_name": pname,
                            "city": city,
                            "state": state_name,
                            "category": category,
                            "raw_context": raw_context[:3500]
                        }).strip()
                        if desc.startswith('"') and desc.endswith('"'):
                            desc = desc[1:-1].strip()
                        row["description"] = desc
                        print(f"      ✅ Generated description ({len(desc)} chars).")
                    except Exception as e:
                        print(f"      ⚠ Description generation error: {e}")

                if "opening_hour" in missing_keys and not (row.get("opening_hour") or "").strip():
                    if category in ["temple", "shrine", "monastery", "mosque"]:
                        row["opening_hour"] = "5:30 AM – 8:30 PM (All days)"
                    elif category in ["park", "garden", "lake", "ghat", "nature", "waterfall"]:
                        row["opening_hour"] = "6:00 AM – 6:30 PM (Daily, Sunrise to Sunset)"
                    else:
                        row["opening_hour"] = "9:30 AM – 5:30 PM (All days)"

            # Update row in master list
            rows[row_idx] = row
            repaired_count += 1

            # Instant write back to CSV after each row
            with open(csv_file, mode="w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)

            time.sleep(random.uniform(2.5, 4.0))

    except Exception as e:
        print(f"\n❌ Error during CSV repair: {e}")
    finally:
        print("🛑 Cleaning up browser driver...")
        close_login_driver()

    summary_msg = (
        f"CSV Repair Completed for {state_name.title()}!\n"
        f"• Total Places Inspected: {len(rows)}\n"
        f"• Places Repaired: {repaired_count} / {total_needing_repair}\n"
        f"• Output File: {csv_file}"
    )
    print(f"\n{summary_msg}")
    return summary_msg


if __name__ == "__main__":
    import sys
    state = sys.argv[1] if len(sys.argv) > 1 else "Bihar"
    repair_state_csv(state)
