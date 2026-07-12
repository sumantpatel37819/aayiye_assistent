"""
agent/tools/sheet_enricher_tool.py

Fetches data for tourist places from Wikipedia + Google Search,
rewrites everything through llama3.2, and returns structured rows
ready to be written to Google Sheets.

Pipeline per place:
  1. Wikipedia REST API  → title, extract, coordinates, images (jpg/jpeg/png)
  2. [FALLBACK] Agar extract khaali/chota ho:
       a. Google Search (Selenium) → correct Wikipedia URL dhundo
       b. crawl4ai (Playwright)    → us URL se text + images + coordinates extract karo
  3. Selenium Google Search → address, transport, food fields
  4. LLM rewrite         → every text field rewritten — no raw copy-paste
  5. Return structured row matching CSV column format
"""

import json
import re
import time
import random
from pathlib import Path

import requests
from langchain_core.tools import tool
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama.llms import OllamaLLM

# ─────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────

DB_DIR = Path(__file__).parent.parent.parent / "sheet_works" / "db" / "Plces_db"

WIKI_SUMMARY  = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
WIKI_MEDIA    = "https://en.wikipedia.org/api/rest_v1/page/media-list/{title}"
WIKI_SEARCH   = "https://en.wikipedia.org/w/api.php"
HEADERS       = {"User-Agent": "AayieAssistant/1.0 (educational project)"}

ALLOWED_EXT   = (".jpg", ".jpeg", ".png")
MIN_IMG_WIDTH = 100   # filter out tiny icons

# ─────────────────────────────────────────────
# LLM Setup
# ─────────────────────────────────────────────

_model = OllamaLLM(model="llama3.2", keep_alive=-1)


# Field-specific rewrite prompts
_PROMPTS = {
    "description": """You are a travel content writer. 
Write a clear, engaging tourist description of "{place}" in {state} in 3-4 sentences.
Focus on what makes it unique and why tourists should visit.
Use ONLY the information in the raw content below. Do not add facts not present in the source.

Raw Content:
{raw}

Tourist Description (3-4 sentences, English only):""",

    "recognition": """You are a travel content writer.
Write 3-4 sentences about the significance and recognition of "{place}" in {state}.
Cover: why it is important, any official recognition (ASI, UNESCO, government awards), and its reputation.
Use ONLY the information in the raw content below.

Raw Content:
{raw}

Recognition & Significance (3-4 sentences, English only):""",

    "culture": """You are a travel content writer.
Describe the local culture around "{place}" in {state} in 3-4 sentences.
Focus on: local traditions, festivals celebrated here, cultural practices, and what visitors experience.
Use ONLY the information in the raw content below.

Raw Content:
{raw}

Local Culture (3-4 sentences, English only):""",

    "history": """You are a travel content writer.
Write a concise historical account of "{place}" in {state} in 3-4 sentences.
Cover: when it was built/founded, key historical events, rulers or builders, and its historical significance.
Use ONLY the information in the raw content below.

Raw Content:
{raw}

History (3-4 sentences, English only):""",

    "address": """You are a travel assistant.
Write the distance and route from the state capital to "{place}" in {state}.
Format: "[X] km from [Capital]. Best route: via [road/highway]."
Use ONLY the information in the raw content below. If not available, write "Distance from capital not found."

Raw Content:
{raw}

Distance from Capital (1-2 lines, English only):""",

    "transport": """You are a travel assistant.
List the available modes of transport to reach "{place}" in {state}.
Format as bullet points: By Train, By Bus, By Air, By Road — include key stops/stations if available.
Use ONLY the information in the raw content below.

Raw Content:
{raw}

Transport Options (bullet points, English only):""",

    "food": """You are a travel food writer.
List 4-6 famous local dishes or foods associated with "{place}" in {state}.
Write as a comma-separated list. Include a very brief note (3-5 words) for each dish.
Use ONLY the information in the raw content below.

Raw Content:
{raw}

Famous Local Food (comma-separated list, English only):""",
}


def _rewrite(field: str, raw: str, place: str, state: str) -> str:
    """Pass raw text through LLM with field-specific prompt."""
    if not raw or not raw.strip():
        return ""
    prompt_text = _PROMPTS.get(field, "Summarize the following in 3 sentences:\n{raw}")
    # Force LLM to return nothing if data is missing
    prompt_text += "\nIf the raw content does not contain relevant information, output NOTHING (an empty string). Do not write 'unfortunately' or 'no information'."
    
    prompt = ChatPromptTemplate.from_template(prompt_text)
    chain  = prompt | _model
    try:
        result = chain.invoke({
            "place": place,
            "state": state,
            "raw": raw[:6000]  # keep within context window
        })
        res_str = result.strip()
        
        # Post-processing to catch LLM apologies
        lower_res = res_str.lower()
        if any(bad_phrase in lower_res for bad_phrase in [
            "unfortunately", "no information", "not mentioned", 
            "does not provide", "not available", "missing"
        ]) and len(res_str) < 150:
            return ""
            
        return res_str
    except Exception as e:
        print(f"    ⚠ LLM rewrite failed for '{field}': {e}")
        return raw[:500]  # fallback: truncated raw


# ─────────────────────────────────────────────
# Wikipedia Fetcher
# ─────────────────────────────────────────────

def _wiki_search_title(place_name: str, state: str) -> tuple[str, str]:
    """
    Wikipedia page title dhundo.
    Returns: (title, google_fallback_text)
      - title: Wikipedia page title (ya place_name as fallback)
      - google_fallback_text: Google se jo text mila (tourism/govt site) — Wikipedia na mile toh use karo
    """
    try:
        for query in [f"{place_name} {state}", place_name]:
            time.sleep(random.uniform(1.5, 3.0))
            resp = requests.get(WIKI_SEARCH, params={
                "action": "opensearch", "search": query,
                "limit": 1, "namespace": 0, "format": "json"
            }, headers=HEADERS, timeout=10)
            data = resp.json()
            print(f"    🕵️ Wikipedia search results for '{query}': {data[1]}, form title finding")
            if data[1]:
                return data[1][0], ""  # Wikipedia title mila — no google text needed
    except Exception as e:
        print(f"    ⚠ Wikipedia opensearch error: {e}")

    # Fallback: Google Search se Wikipedia URL ya tourism page text lo
    print(f"    ⚠ Wikipedia API couldn't find title. Trying Google Search fallback for '{place_name} {state} wikipedia'")
    from gettinglinks.selenium_search import search_and_extract_text
    import urllib.parse
    try:
        res = search_and_extract_text(f"{place_name} {state} wikipedia", num_results=1)
        if res and len(res) > 0:
            r      = res[0]
            url    = r[2] if len(r) > 2 else ""
            g_text = r[0] if len(r) > 0 else ""   # index 0 = extracted page text

            if "wikipedia.org/wiki/" in url:
                title_from_url = url.split("wikipedia.org/wiki/")[1].split("#")[0].replace("_", " ")
                title_from_url = urllib.parse.unquote(title_from_url)
                print(f"    ✅ Found Wikipedia title via Google: {title_from_url}")
                return title_from_url, g_text   # Wikipedia title + page text
            elif g_text and len(g_text) > 200:
                # Non-Wikipedia page mila (tourism/govt) — text valuable hai
                print(f"    📄 Non-Wikipedia page se text mila ({len(g_text)} chars): {url}")
                return place_name, g_text
    except Exception as e:
        print(f"    ⚠ Google Search fallback error: {e}")

    return place_name, ""


def _fetch_images_via_crawl4ai(wiki_url: str, place_name: str) -> list:
    """
    crawl4ai se Wikipedia page se images fetch karo (fallback jab API se < 2 images aayein).
    """
    print(f"    🕷 [crawl4ai] Image fallback for: {place_name} ({wiki_url})")
    try:
        from scraping_web.wiki_crawl4ai import scrape_wikipedia_sync
        data = scrape_wikipedia_sync(wiki_url)
        imgs = data.get("images", [])
        print(f"    🖼 [crawl4ai] Image fallback mili: {len(imgs)} images")
        return imgs
    except Exception as e:
        print(f"    ⚠ [crawl4ai] Image fallback error: {e}")
        return []


def fetch_wikipedia_data(place_name: str, state: str) -> dict:
    """
    Fetch Wikipedia summary, coordinates, and images for a place.

    Pipeline:
      1. Wikipedia REST API (title se) → extract, coordinates
      2. [FALLBACK] Agar extract khaali/chota (<100 chars):
           a. Google Search → correct Wikipedia URL dhundo
           b. crawl4ai → us URL se text + images + coordinates extract karo
      3. Images: API se fetch karo; agar < 2 mili toh crawl4ai image fallback

    Returns: {title, extract, lat, lon, images: [...], wiki_url}
    """
    result = {
        "title": place_name, "extract": "", "lat": None, "lon": None,
        "images": [], "wiki_url": ""
    }

    wiki_title, google_fallback_text = _wiki_search_title(place_name, state)
    encoded_title = requests.utils.quote(wiki_title.replace(" ", "_"))

    # ── Step 1: Summary via REST API (extract + coordinates) ────────
    api_success = False
    try:
        time.sleep(random.uniform(1.5, 3.0))
        resp = requests.get(
            WIKI_SUMMARY.format(title=encoded_title),
            headers=HEADERS, timeout=12
        )
        if resp.status_code == 200:
            data = resp.json()
            result["title"]    = data.get("title", place_name)
            result["extract"]  = data.get("extract", "")
            result["wiki_url"] = data.get("content_urls", {}).get("desktop", {}).get("page", "")

            coords = data.get("coordinates", {})
            if coords:
                result["lat"] = coords.get("lat")
                result["lon"] = coords.get("lon")
                print(f"    📍 Wikipedia API coordinates: {result['lat']}, {result['lon']}")
            else:
                print(f"    ⚠ No coordinates on Wikipedia API for '{wiki_title}'")

            if result["extract"] and len(result["extract"]) >= 100:
                api_success = True
                print(f"    ✅ Wikipedia API extract mila: {len(result['extract'])} chars")
            else:
                print(f"    ⚠ Wikipedia API extract khaala/chota: '{result['extract'][:80]}...'")
        else:
            print(f"    ⚠ Wikipedia API status: {resp.status_code} for '{wiki_title}'")
    except Exception as e:
        print(f"    ⚠ Wikipedia summary error: {e}")

    # ── Step 1.5: Coordinates-only crawl4ai fallback ──────────────
    # Jab API extract OK ho lekin lat/lon na aaye (e.g., Nalanda mahavihara)
    if api_success and result["lat"] is None and result.get("wiki_url"):
        print(f"    🔄 Extract OK lekin coordinates missing — crawl4ai se try kar raha hoon...")
        try:
            from scraping_web.wiki_crawl4ai import scrape_wikipedia_sync
            coord_data = scrape_wikipedia_sync(result["wiki_url"])
            if coord_data.get("lat"):
                result["lat"] = coord_data["lat"]
                result["lon"] = coord_data["lon"]
                print(f"    📍 [crawl4ai] Coordinates mili: {result['lat']}, {result['lon']}")
            else:
                print(f"    ⚠ [crawl4ai] Coordinates abhi bhi nahi mili Wikipedia page pe")
        except Exception as ce:
            print(f"    ⚠ [crawl4ai] Coordinate-only fetch error: {ce}")

    # ── Step 2: crawl4ai FALLBACK — agar API se extract nahi aaya ───
    if not api_success:
        print(f"    🔄 Wikipedia API fail — crawl4ai fallback shuru ho raha hai...")

        # Step 2a: Google se correct Wikipedia URL dhundo
        wiki_url_for_scrape = result.get("wiki_url", "")

        if not wiki_url_for_scrape:
            print(f"    🌐 Google search kar raha hoon: '{place_name} {state} wikipedia'")
            try:
                from gettinglinks.selenium_search import search_and_extract_text
                import urllib.parse as _uparse
                search_results = search_and_extract_text(
                    f"{place_name} {state} wikipedia site:en.wikipedia.org", num_results=1
                )
                for res in (search_results or []):
                    if res and len(res) > 2:
                        candidate_url = res[2]
                        if "wikipedia.org/wiki/" in (candidate_url or ""):
                            wiki_url_for_scrape = candidate_url
                            print(f"    ✅ Wikipedia URL mila Google se: {wiki_url_for_scrape}")
                            # Agar text mila toh use bhi lo
                            if not google_fallback_text and res[0] and len(res[0]) > 200:
                                google_fallback_text = res[0]
                            break
            except Exception as ge:
                print(f"    ⚠ Google search for wiki URL failed: {ge}")

            # LAST RESORT: Direct Wikipedia URL construct karo — lekin sirf agar
            # google_fallback_text bhi khaali hai (matlab kuch bhi nahi mila)
            if not wiki_url_for_scrape and not google_fallback_text:
                direct_url = f"https://en.wikipedia.org/wiki/{wiki_title.replace(' ', '_')}"
                print(f"    🔗 Direct Wikipedia URL try kar raha hoon: {direct_url}")
                wiki_url_for_scrape = direct_url
            elif not wiki_url_for_scrape and google_fallback_text:
                print(f"    📄 Wikipedia URL nahi mila — Google text use kar raha hoon ({len(google_fallback_text)} chars)")

        # Step 2b: crawl4ai se Wikipedia page scrape karo (sirf real wiki URLs ke liye)
        if wiki_url_for_scrape and "wikipedia.org/wiki/" in wiki_url_for_scrape:
            try:
                from scraping_web.wiki_crawl4ai import scrape_wikipedia_sync
                crawl_data = scrape_wikipedia_sync(wiki_url_for_scrape)

                if crawl_data.get("success"):
                    # Extract — sirf tabhi overwrite karo jab crawl ne better data diya ho
                    if crawl_data["extract"] and len(crawl_data["extract"]) > len(result["extract"]):
                        result["extract"] = crawl_data["extract"]
                        print(f"    ✅ [crawl4ai] Extract update: {len(result['extract'])} chars")

                    # Coordinates — sirf tabhi overwrite karo jab API ne nahi diye
                    if not result["lat"] and crawl_data.get("lat"):
                        result["lat"] = crawl_data["lat"]
                        result["lon"] = crawl_data["lon"]
                        print(f"    📍 [crawl4ai] Coordinates update: {result['lat']}, {result['lon']}")

                    # Images from crawl4ai (will be merged below with API images)
                    if crawl_data.get("images"):
                        for img_url in crawl_data["images"]:
                            if img_url not in result["images"]:
                                result["images"].append(img_url)
                        print(f"    🖼 [crawl4ai] {len(crawl_data['images'])} images add kiye")

                    # wiki_url update karo agar pehle se khaali tha
                    if not result["wiki_url"]:
                        result["wiki_url"] = wiki_url_for_scrape
                else:
                    print(f"    ⚠ [crawl4ai] Scrape unsuccessful for: {wiki_url_for_scrape}")
            except Exception as ce:
                print(f"    ⚠ [crawl4ai] Fallback error: {ce}")
        else:
            print(f"    ⚠ Wikipedia URL nahi mila — crawl4ai fallback skip")

        # Step 2c: Agar crawl4ai bhi fail hua aur google_fallback_text available hai — use karo
        if not result["extract"] and google_fallback_text:
            result["extract"] = google_fallback_text
            print(f"    📄 Google fallback text use kar raha hoon: {len(google_fallback_text)} chars")

    # ── Step 3: Images via Wikipedia API ────────────────────────────
    api_images_before = len(result["images"])
    try:
        params_images = {
            "action": "query",
            "format": "json",
            "titles": wiki_title,
            "prop": "images",
            "imlimit": "max",
        }
        time.sleep(random.uniform(1.5, 3.0))
        resp2 = requests.get(WIKI_SEARCH, params=params_images, headers=HEADERS, timeout=12)
        if resp2.status_code == 200:
            data2 = resp2.json()
            image_titles = []
            for page_id, page_data in data2.get("query", {}).get("pages", {}).items():
                if "images" in page_data:
                    for img in page_data["images"]:
                        image_titles.append(img["title"])

            for title in image_titles:
                ext = Path(title).suffix.lower()
                if ext not in ALLOWED_EXT:
                    continue

                params_imginfo = {
                    "action": "query",
                    "format": "json",
                    "titles": title,
                    "prop": "imageinfo",
                    "iiprop": "url"
                }
                time.sleep(random.uniform(1.0, 2.5))
                r = requests.get(WIKI_SEARCH, params=params_imginfo, headers=HEADERS, timeout=12)
                if r.status_code == 200:
                    img_data = r.json()
                    for pid, pdata in img_data.get("query", {}).get("pages", {}).items():
                        if "imageinfo" in pdata:
                            url = pdata["imageinfo"][0].get("url")
                            if url and url not in result["images"]:
                                result["images"].append(url)
    except Exception as e:
        print(f"    ⚠ Wikipedia media API error: {e}")

    # ── Step 4: Image FALLBACK — agar abhi bhi < 2 images hain ─────
    if len(result["images"]) < 2 and result.get("wiki_url"):
        print(f"    🔄 Image fallback: sirf {len(result['images'])} image(s) mili — crawl4ai try kar raha hoon...")
        crawl_imgs = _fetch_images_via_crawl4ai(result["wiki_url"], place_name)
        for img_url in crawl_imgs:
            if img_url not in result["images"]:
                result["images"].append(img_url)
        print(f"    🖼 Image fallback ke baad total: {len(result['images'])} images")

    print(f"    📊 Final Wikipedia result — extract: {len(result['extract'])} chars, "
          f"images: {len(result['images'])}, coords: ({result['lat']}, {result['lon']})")

    return result


# ─────────────────────────────────────────────
# Google Search Fallback (Selenium)
# ─────────────────────────────────────────────

def _google_search_text(query: str) -> tuple[str, list]:
    """Use existing Selenium scraper to get text and urls for a query."""
    try:
        from gettinglinks.selenium_search import search_and_extract_text, close_browser as _cb

        # Fresh browser session = CAPTCHA se bachao
        _cb()
        time.sleep(random.uniform(4.0, 7.0))   # Google cooldown

        results = search_and_extract_text(query, num_results=2)

        combined_text = ""
        urls = []
        if results:
            for res in results:
                if res and res[0]:
                    combined_text += res[0] + "\n\n"
                if res and len(res) > 2 and res[2]:
                    urls.append(res[2])

        return combined_text.strip()[:5000], urls

    except Exception as e:
        print(f"    ⚠ Google fallback error: {e}")
    return "", []


# ─────────────────────────────────────────────
# State JSON Loader
# ─────────────────────────────────────────────

def _load_state_places(state_name: str, city_filter: str = None) -> list:
    """
    Load places from state JSON file.
    Returns list of: {place_name, city, state, lat, lon, keywords}
    """
    # Normalize state name for filename
    state_key = state_name.lower().replace(" ", "_").replace("-", "_")
    json_file  = DB_DIR / f"places-name-{state_key}.json"

    if not json_file.exists():
        # Try partial match
        matches = list(DB_DIR.glob(f"places-name-*{state_key}*.json"))
        if matches:
            json_file = matches[0]
        else:
            raise FileNotFoundError(
                f"No JSON file found for state '{state_name}'.\n"
                f"Available: {[f.name for f in DB_DIR.glob('places-name-*.json')]}"
            )

    print(f"  📂 Loading: {json_file.name}")
    data = json.loads(json_file.read_text(encoding="utf-8"))

    places = []
    # Navigate nested structure: india → state → city → places
    india   = data.get("india", data)
    state_d = next(iter(india.values())) if india else {}

    for city, city_data in state_d.items():
        if city_filter and city_filter.lower() not in city.lower():
            continue
        city_places = city_data.get("places", [])
        for p in city_places:
            places.append({
                "name":     p.get("name", ""),
                "city":     city,
                "state":    state_name,
                "lat":      p.get("lat"),
                "lon":      p.get("lon"),
                "category": p.get("category", ""),
                "keywords": p.get("keywords", []),
                "description": p.get("description", ""),
            })

    return places


# ─────────────────────────────────────────────
# Main Enricher
# ─────────────────────────────────────────────

CSV_COLUMNS = [
    "Id", "district", "Place", "famous_place_name", "famous_place_title",
    "Description", "Recognition", "culture", "Location",
    "Address_from_Capital", "means_of_transport", "Famous_Dish",
    "History", "reference", "Temple_reference", "Image URL from wikipedia",
    "Google Search Links"
]


def enrich_state_places(state_name: str, city_name: str = None) -> str:
    """Use this tool to add, enrich, or fetch tourist places for a specific Indian State or City and put them into the Google Sheet. (e.g. 'Bihar ke nalanda place ko sheet me daalo', 'Enrich Rajasthan').
    
    Args:
        state_name (str): The name of the Indian state (e.g. "Bihar", "Rajasthan").
        city_name (str, optional): The name of the city (e.g. "Nalanda"). Leave as None if not specified.
        
    Returns:
        str: A summary of the enrichment process.
    """
    places = _load_state_places(state_name, city_filter=city_name)
    if not places:
        return "No places found."

    print(f"\n  🗺 {len(places)} places found"
          f"{f' in {city_name}' if city_name else ''} for {state_name}")
          
    # ── Fetch existing places from sheet ──────────
    from gettinglinks.selenium_search import search_and_extract_text, close_browser
    from agent.tools.sheets_tool import get_existing_places_from_sheet, update_enriched_row_in_sheet, write_enriched_rows_to_sheet
    existing_places = get_existing_places_from_sheet(state_name.title())

    rows = []

    for idx, place in enumerate(places, start=1):
        pname  = place["name"]
        city   = place["city"].replace("_", " ").title()
        state  = state_name

        print(f"\n  [{idx}/{len(places)}] Processing: {pname}")
        
        # ── Check Duplicate / Missing Fields ─────────────
        pname_lower = pname.lower()
        is_existing = pname_lower in existing_places
        row_idx_to_update = None
        
        if is_existing:
            row_info = existing_places[pname_lower]
            row_data = row_info["data"]
            row_idx_to_update = row_info["row_index"]
            
            # Required columns (0-indexed based on CSV_COLUMNS):
            # 5: Description, 9: Address_from_Capital, 10: means_of_transport
            # 11: Famous_Dish, 12: History, 15: Image URL from wikipedia
            desc_val      = row_data[5].strip()  if len(row_data) > 5  else ""
            addr_val      = row_data[9].strip()  if len(row_data) > 9  else ""
            transport_val = row_data[10].strip() if len(row_data) > 10 else ""
            food_val      = row_data[11].strip() if len(row_data) > 11 else ""
            hist_val      = row_data[12].strip() if len(row_data) > 12 else ""
            img_val       = row_data[15].strip() if len(row_data) > 15 else ""

            all_filled = desc_val and hist_val and img_val and addr_val and transport_val and food_val

            if all_filled:
                print(f"    ✅ Already filled completely: {pname} (Skipping)")
                continue
            elif desc_val and hist_val and addr_val and transport_val and food_val and not img_val:
                print(f"    🖼️ Text+address filled, but images missing. Fetching only images for: {pname}")
                
                # Fetch only images
                wiki = fetch_wikipedia_data(pname, state)
                image_urls = ", ".join(wiki["images"][:8])
                
                # Reconstruct row with old data + new images
                row_dict = {}
                for i, col in enumerate(CSV_COLUMNS):
                    val = row_data[i] if i < len(row_data) else ""
                    row_dict[col] = val
                row_dict["Image URL from wikipedia"] = image_urls
                
                # Update in sheet directly
                flat_row = [row_dict.get(col, "") for col in CSV_COLUMNS]
                res_msg = update_enriched_row_in_sheet(state.title(), row_idx_to_update, flat_row)
                print(f"    {res_msg}")
                continue
            else:
                print(f"    🔄 Partially filled. Updating missing fields for: {pname}")

        # ── 0. Existing row ko base banao (existing data preserve karo) ──
        # Agar row sheet mein hai toh uske data se row_dict seed karo
        if is_existing:
            base_row = existing_places[pname_lower]["data"]
            row_dict = {}
            for i, col in enumerate(CSV_COLUMNS):
                row_dict[col] = base_row[i].strip() if i < len(base_row) else ""
            # Id aur basic fields ensure karo
            row_dict["Id"]                = row_dict.get("Id") or str(idx)
            row_dict["district"]          = row_dict.get("district") or city
            row_dict["Place"]             = row_dict.get("Place") or city
            row_dict["famous_place_name"] = row_dict.get("famous_place_name") or pname
            
            if not row_dict.get("Description") and place.get("description"):
                row_dict["Description"] = place["description"]
        else:
            row_dict = {col: "" for col in CSV_COLUMNS}
            row_dict["Id"]                = str(idx)
            row_dict["district"]          = city
            row_dict["Place"]             = city
            row_dict["famous_place_name"] = pname
            
            if place.get("description"):
                row_dict["Description"] = place["description"]

        # Kaunse fields fill karne hain decide karo
        need_text   = not (row_dict.get("Description") and row_dict.get("History"))
        need_addr   = not row_dict.get("Address_from_Capital")
        need_trans  = not row_dict.get("means_of_transport")
        need_food   = not row_dict.get("Famous_Dish")
        need_img    = not row_dict.get("Image URL from wikipedia")
        need_google = need_addr or need_trans or need_food

        print(f"    📋 Missing fields — text:{need_text} addr:{need_addr} "
              f"transport:{need_trans} food:{need_food} img:{need_img}")

        wiki = None
        extract = ""

        # ── 1. Wikipedia — sirf tab chalao agar text/img/coords missing hai ──
        if need_text or need_img or not row_dict.get("Location") or not row_dict.get("reference"):
            wiki = fetch_wikipedia_data(pname, state)
            extract = wiki["extract"]

            # ── 1a. Browser reset — CAPTCHA avoid ke liye ──────────────
            print(f"    🔄 Browser reset kar raha hoon (fresh session for Google searches)...")
            close_browser()
            time.sleep(3)

            # Coordinates (Wikipedia first, JSON fallback)
            if not row_dict.get("Location") or row_dict.get("Location") == "Location not found":
                lat = wiki["lat"] or place["lat"]
                lon = wiki["lon"] or place["lon"]
                row_dict["Location"] = f"{lat}°N, {lon}°E" if lat and lon else "Location not found"

            # reference (wiki URL)
            if not row_dict.get("reference") and wiki.get("wiki_url"):
                row_dict["reference"] = wiki["wiki_url"]

            # famous_place_title
            if not row_dict.get("famous_place_title") and wiki.get("title"):
                row_dict["famous_place_title"] = wiki["title"]
        else:
            # Wikipedia nahi chahiye — sirf Google searches ke liye browser reset karo
            if need_google:
                close_browser()
                time.sleep(2)

        # ── 2. LLM Rewrite — sirf khaali text fields ke liye ──────────
        if need_text and extract:
            print(f"    ✍ LLM rewriting missing text fields...")
            if not row_dict.get("Description"):
                row_dict["Description"] = _rewrite("description", extract, pname, state)
                time.sleep(0.3)
            if not row_dict.get("Recognition"):
                row_dict["Recognition"] = _rewrite("recognition", extract, pname, state)
                time.sleep(0.3)
            if not row_dict.get("culture"):
                row_dict["culture"] = _rewrite("culture", extract, pname, state)
                time.sleep(0.3)
            if not row_dict.get("History"):
                row_dict["History"] = _rewrite("history", extract, pname, state)
                time.sleep(0.3)
        elif need_text:
            print(f"    ⚠ Text fields khaali hain lekin Wikipedia extract nahi mila")

        # ── 3. Google Search — sirf khaali fields ke liye ─────────────
        all_google_links = list(filter(None, row_dict.get("Google Search Links", "").splitlines()))

        if need_addr:
            address_raw, address_urls = _google_search_text(
                f"{pname} {state} distance from state capital how to reach"
            )
            row_dict["Address_from_Capital"] = _rewrite("address", address_raw, pname, state)
            all_google_links += [u for u in address_urls if u and u not in all_google_links]

        if need_trans:
            transport_raw, transport_urls = _google_search_text(
                f"{pname} {state} how to reach by train bus road"
            )
            row_dict["means_of_transport"] = _rewrite("transport", transport_raw, pname, state)
            all_google_links += [u for u in transport_urls if u and u not in all_google_links]

        if need_food:
            food_raw, food_urls = _google_search_text(
                f"famous food dishes near {pname} {state}"
            )
            row_dict["Famous_Dish"] = _rewrite("food", food_raw, pname, state)
            all_google_links += [u for u in food_urls if u and u not in all_google_links]

        if all_google_links:
            row_dict["Google Search Links"] = "\n".join(all_google_links)

        # ── 4. Images — sirf agar missing ho ──────────────────────────
        if need_img:
            if wiki and wiki.get("images"):
                row_dict["Image URL from wikipedia"] = ", ".join(wiki["images"][:8])
            else:
                # Wiki nahi chala tha — abhi fetch karo sirf images ke liye
                _wiki_img = fetch_wikipedia_data(pname, state)
                if _wiki_img.get("images"):
                    row_dict["Image URL from wikipedia"] = ", ".join(_wiki_img["images"][:8])

        rows.append(row_dict)

        # ── 5. Write or Update Sheet immediately ──────────────────────
        try:
            if is_existing and row_idx_to_update:
                flat_row = [row_dict.get(col, "") for col in CSV_COLUMNS]
                # Original ID preserve karo
                orig_id = existing_places[pname_lower]["data"][0] if existing_places[pname_lower]["data"] else str(idx)
                flat_row[0] = orig_id

                res_msg = update_enriched_row_in_sheet(state_name.title(), row_idx_to_update, flat_row)
                print(f"    ✅ Updated: {pname} -> {res_msg}")
            else:
                res_msg = write_enriched_rows_to_sheet(state_name.title(), [row_dict])
                print(f"    ✅ Appended: {pname} -> {res_msg}")
        except Exception as sheet_err:
            print(f"    ⚠ Error processing {pname}: {sheet_err}")

        # Browser cleanup
        print(f"    🛑 Closing browser for {pname} to reset session...")
        close_browser()

    return f"Successfully processed the requested places for the '{state_name.title()}' tab."
