"""
agent/tools/create_csv_tool.py

Pipeline to generate rich tourist destination CSV files for any state:
Target: sheet_works/db/details_places/<state_lower>_places.csv

Columns:
  place_id, name, state, city, category, coordinate, opening_hour,
  avg_time_spend, entry_fee, best_time_to_visit, other_names, description

Features:
  - Loads places from sheet_works/db/Plces_db/places-name-<state>.json
  - Coordinates via Google Places API (GOOGLE_PLACES_API_KEY in .env, blank if no response)
  - Rich fields via Live Google Chrome AI Overview + Ollama LLM structured extraction
  - In-depth best_time_to_visit tailored for recommendation engines (Couples, Families, Season, Best hours)
  - Incremental resume & deduplication
  - TaskController integration for GUI progress bar, pause, resume, and stop
"""

import os
import csv
import json
import time
import random
import requests
from pathlib import Path
from dotenv import load_dotenv

from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama.llms import OllamaLLM

from gettinglinks.google_login_search import search_and_extract_gemini_and_links, close_login_driver
from agent.task_controller import task_controller

load_dotenv()

import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Directories
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
PLACES_DB_DIR = PROJECT_ROOT / "sheet_works" / "db" / "Plces_db"
CSV_OUTPUT_DIR = PROJECT_ROOT / "sheet_works" / "db" / "details_places"
CSV_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

GOOGLE_PLACES_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY", "")

CSV_HEADERS = [
    "place_id",
    "name",
    "state",
    "city",
    "category",
    "coordinate",
    "opening_hour",
    "avg_time_spend",
    "entry_fee",
    "best_time_to_visit",
    "other_names",
    "description"
]

# LLM for structuring extracted AI Overview into clean fields
_llm = OllamaLLM(model="llama3.2", keep_alive=-1)

_PROMPT_EXTRACT = ChatPromptTemplate.from_template(
    """You are an expert travel data curator for an intelligent tourism recommendation platform.
Extract and synthesize structured tourism information about "{place_name}" located in {city}, {state} (Category: {category}) using the raw search context below.

Raw Search Context:
{raw_context}

Output ONLY valid JSON with EXACTLY the following keys:
{{
  "opening_hour": "Accurate daily/weekly opening and closing timings, e.g., '6:00 AM – 9:00 PM (All days)' or '9:30 AM – 5:30 PM (Closed on Mondays)'. Mention special morning/evening aarti or ritual timings if applicable.",
  "avg_time_spend": "Recommended duration of visit, e.g., '1 to 2 hours' or '2 to 3 hours' or 'Half day (3-4 hours)'.",
  "entry_fee": "Accurate entry ticket pricing. E.g., 'Free entry' or '₹20 for Indians, ₹100 for Foreigners, Free for children under 5'. Include camera fees if mentioned.",
  "best_time_to_visit": "DETAILED RECOMMENDATION FOR SMART TRAVELER RECOMMENDATION ENGINE. Include: 1) Ideal months/seasons (e.g. October to March for pleasant climate); 2) Best time of day (e.g. Early morning 6-8 AM for peaceful darshan/photography, or 4-6 PM for sunset views & Ganga aarti); 3) Traveler persona recommendations: Couple friendly (romantic sunset walks, scenic view), Family & Kids suitability (parks, boat rides, safety), Solo/Devotees; 4) Key festivals & season warnings (e.g. avoid peak summer afternoons).",
  "other_names": "Alternate, historical, local, or vernacular names (e.g., 'Bari Patan Devi, Patneshwari'). If none, return empty string.",
  "description": "Engaging, informative 3-4 sentence narrative covering the historical heritage, architectural highlights, significance, and unique tourist experience."
}}

JSON:"""
)


def load_state_json_places(state_name: str, city_filter: str = None) -> list:
    """
    Load places from sheet_works/db/Plces_db/places-name-<state>.json.
    Returns list of dicts: {name, state, city, category, lat, lon}
    """
    state_slug = state_name.lower().strip().replace(" ", "_").replace("-", "_")
    target_file = PLACES_DB_DIR / f"places-name-{state_slug}.json"

    if not target_file.exists():
        # Fallback search by partial match
        matches = list(PLACES_DB_DIR.glob(f"places-name-*{state_slug}*.json"))
        if matches:
            target_file = matches[0]
        else:
            print(f"  [ERR] State JSON file not found for '{state_name}' in {PLACES_DB_DIR}")
            return []

    print(f"  [FILE] Loading state database: {target_file.name}")
    try:
        data = json.loads(target_file.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  ❌ Error reading {target_file.name}: {e}")
        return []

    places = []
    # Handle {"india": {<state>: {<city>: {"places": [...]}}}} or flat structures
    country_data = data.get("india", data)
    state_data = next(iter(country_data.values())) if country_data else {}

    city_filter_lower = city_filter.strip().lower() if city_filter else None

    for city_key, city_info in state_data.items():
        city_display = city_key.replace("_", " ").title()
        if city_filter_lower and city_filter_lower not in city_key.lower():
            continue

        raw_places = city_info.get("places", []) if isinstance(city_info, dict) else []
        for p in raw_places:
            pname = p.get("name", "").strip()
            if not pname:
                continue
            places.append({
                "name": pname,
                "state": state_name.title(),
                "city": city_display,
                "category": p.get("category", p.get("type", "tourist attraction")),
                "fallback_lat": p.get("lat"),
                "fallback_lon": p.get("lon"),
            })

    return places


def get_place_coordinates(place_name: str, city: str, state: str) -> str:
    """
    Google Places API se coordinate (lat, lng) fetch karo.
    Agar response na mile ya failure ho, toh blank ('') return karo.
    """
    if not GOOGLE_PLACES_API_KEY:
        return ""

    query = f"{place_name}, {city}, {state}"
    url = (
        f"https://maps.googleapis.com/maps/api/place/findplacefromtext/json"
        f"?input={requests.utils.quote(query)}"
        f"&inputtype=textquery"
        f"&fields=geometry,name"
        f"&key={GOOGLE_PLACES_API_KEY}"
    )

    try:
        resp = requests.get(url, timeout=8)
        if resp.status_code == 200:
            data = resp.json()
            candidates = data.get("candidates", [])
            if candidates:
                loc = candidates[0].get("geometry", {}).get("location", {})
                lat = loc.get("lat")
                lng = loc.get("lng")
                if lat is not None and lng is not None:
                    return f"{lat}, {lng}"
    except Exception as e:
        print(f"    [WARN] Google Places API coordinate error for '{place_name}': {e}")

    # Blank if Google Places API does not respond / finds nothing
    return ""


def extract_place_details_ai(place_name: str, city: str, state: str, category: str) -> dict:
    """
    Google Chrome AI Mode (Live search) se data extract karke
    Ollama LLM se structured fields generate karo.
    """
    search_query = f"{place_name} {city} {state} opening hours entry fee avg time spend best time to visit other names description"
    print(f"    🌐 Chrome AI Search: '{search_query}'")

    raw_text = search_and_extract_gemini_and_links(search_query, num_results=2)
    if not raw_text or len(raw_text.strip()) < 50:
        print(f"    ⚠ Live Search se text nahi mila for '{place_name}'. Direct knowledge base try kar rahe hain...")
        raw_text = f"Tourist place: {place_name} in {city}, {state}. Category: {category}."

    # Send to Llama 3.2 for strict JSON extraction
    try:
        chain = _PROMPT_EXTRACT | _llm
        raw_json = chain.invoke({
            "place_name": place_name,
            "city": city,
            "state": state,
            "category": category,
            "raw_context": raw_text[:4000]
        }).strip()

        # Parse JSON
        clean_json = raw_json
        if "```json" in clean_json:
            clean_json = clean_json.split("```json")[1].split("```")[0].strip()
        elif "```" in clean_json:
            clean_json = clean_json.split("```")[1].split("```")[0].strip()

        import re
        match = re.search(r'\{.*\}', clean_json, re.DOTALL)
        if match:
            parsed = json.loads(match.group(0))
            return {
                "opening_hour": parsed.get("opening_hour", "Open daily"),
                "avg_time_spend": parsed.get("avg_time_spend", "1 to 2 hours"),
                "entry_fee": parsed.get("entry_fee", "Free entry"),
                "best_time_to_visit": parsed.get("best_time_to_visit", "October to March; pleasant weather"),
                "other_names": parsed.get("other_names", ""),
                "description": parsed.get("description", "")
            }
    except Exception as e:
        print(f"    [WARN] LLM parsing error: {e}")

    return {
        "opening_hour": "Open daily",
        "avg_time_spend": "1 to 2 hours",
        "entry_fee": "Free entry",
        "best_time_to_visit": "October to March. Early morning or evening recommended. Suitable for couples and families.",
        "other_names": "",
        "description": f"{place_name} is a renowned {category} in {city}, {state}."
    }


def create_state_csv(state_name: str, city_filter: str = None) -> str:
    """
    State ke sabhi places ka data nikal kar CSV file create karo.
    Target: sheet_works/db/details_places/<state_lower>_places.csv
    """
    state_slug = state_name.lower().strip().replace(" ", "_").replace("-", "_")
    csv_filename = f"{state_slug}_places.csv"
    csv_path = CSV_OUTPUT_DIR / csv_filename

    print(f"\n🚀 [CSV Creator] Starting CSV generation for state: '{state_name}'")
    print(f"   Target file: {csv_path}")

    places = load_state_json_places(state_name, city_filter=city_filter)
    if not places:
        return f"❌ No places found for state '{state_name}'. Please verify state name."

    # Read existing places to resume and avoid duplicate work
    existing_place_names = set()
    highest_id = 0

    if csv_path.exists():
        try:
            with open(csv_path, mode="r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    name = (row.get("name") or "").strip().lower()
                    if name:
                        existing_place_names.add(name)
                    try:
                        pid = int(row.get("place_id", 0))
                        if pid > highest_id:
                            highest_id = pid
                    except ValueError:
                        pass
            print(f"   📋 Found {len(existing_place_names)} existing places in {csv_filename}. Resuming from ID {highest_id + 1}...")
        except Exception as e:
            print(f"   ⚠ Error reading existing CSV: {e}")

    # Prepare file: write header if new file
    file_is_new = not csv_path.exists() or os.path.getsize(csv_path) == 0

    task_controller.reset(f"Creating CSV for {state_name}", len(places))
    created_count = 0
    skipped_count = 0

    try:
        with open(csv_path, mode="a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
            if file_is_new:
                writer.writeheader()
                f.flush()

            for idx, place in enumerate(places, start=1):
                pname = place["name"]
                city = place["city"]
                category = place["category"]

                # Task controller checkpoint (Pause/Resume/Cancel)
                if not task_controller.check_point(idx, len(places), pname, f"Creating CSV for {state_name}"):
                    print("  ⏹ CSV generation stopped by user.")
                    break

                # Duplicate check (Skip already filled)
                if pname.lower() in existing_place_names:
                    skipped_count += 1
                    continue

                highest_id += 1
                current_id = highest_id

                print(f"\n  [{idx}/{len(places)}] (ID: {current_id}) Processing: '{pname}' ({city}, {state_name})")

                # 1. Google Places API Coordinate (blank if no response)
                coord = get_place_coordinates(pname, city, state_name)
                if coord:
                    print(f"    📍 Coordinate: {coord} (via Google Places API)")
                else:
                    print(f"    📍 Coordinate: [Blank] (Google Places API did not return location)")

                # 2. Chrome AI Search & Rich Details
                details = extract_place_details_ai(pname, city, state_name, category)

                # 3. Assemble CSV Row
                row_data = {
                    "place_id": current_id,
                    "name": pname,
                    "state": state_name.title(),
                    "city": city,
                    "category": category,
                    "coordinate": coord,
                    "opening_hour": details.get("opening_hour", ""),
                    "avg_time_spend": details.get("avg_time_spend", ""),
                    "entry_fee": details.get("entry_fee", ""),
                    "best_time_to_visit": details.get("best_time_to_visit", ""),
                    "other_names": details.get("other_names", ""),
                    "description": details.get("description", "")
                }

                # 4. Immediate Flush to Disk (Zero data loss)
                writer.writerow(row_data)
                f.flush()
                existing_place_names.add(pname.lower())
                created_count += 1
                print(f"    ✅ Appended ID {current_id} ('{pname}') to {csv_filename}")

                # Human-like randomized delay between places to avoid triggering Google rate-limits
                time.sleep(random.uniform(3.0, 5.0))

    except Exception as e:
        print(f"\n❌ Error during CSV creation: {e}")
    finally:
        print("🛑 Cleaning up browser driver...")
        close_login_driver()

    summary_msg = (
        f"CSV Generation Completed for {state_name.title()}!\n"
        f"• Total Places Processed: {created_count}\n"
        f"• Previously Existing (Skipped): {skipped_count}\n"
        f"• Saved To: {csv_path}"
    )
    print(f"\n{summary_msg}")
    return summary_msg


if __name__ == "__main__":
    import sys
    state = sys.argv[1] if len(sys.argv) > 1 else "Bihar"
    create_state_csv(state)
