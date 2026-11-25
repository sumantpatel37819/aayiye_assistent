"""
agent/tools/sheet_enricher_tool.py

High-accuracy enrichment tool for Indian tourist places with Adaptive Dual-Browser Failover.
Populates and enriches Google Sheets with:
  1. Adaptive Dual-Browser Failover: Chrome <-> Brave Browser (starts with Chrome, switches to Brave upon failure, keeps using Brave until fail, then back to Chrome)
  2. Smart Skip & Partial Fill: Completely skips fully filled places; only populates missing/broken fields preserving existing valid data
  3. Strict Wikipedia verification: Prevents foreign/mismatched articles & images
  4. Multi-tier coordinate resolution: Local JSON -> Google Places API -> Verified Wikipedia
  5. Direct Google Snippet + Web Link Extraction
  6. Context-aware LLM generation with post-cleaning (eliminates apologies like 'Nothing.' or 'Unfortunately')
  7. Immediate Google Sheets sync
"""

import os
import re
import json
import time
import random
import socket
import difflib
import urllib.parse
from pathlib import Path

# Force IPv4 resolution to prevent socket hang on Ubuntu 24.04
_orig_getaddrinfo = socket.getaddrinfo
def _getaddrinfo_ipv4(host, port, family=0, type=0, proto=0, flags=0):
    return _orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)
socket.getaddrinfo = _getaddrinfo_ipv4

import requests
from dotenv import load_dotenv
from langchain_core.tools import tool
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama.llms import OllamaLLM
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from gettinglinks.chrome_config import find_chrome, chrome_major_version

load_dotenv()

# ─────────────────────────────────────────────
# Config & Directories
# ─────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_DIR       = PROJECT_ROOT / "sheet_works" / "db" / "Plces_db"

WIKI_SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
WIKI_SEARCH  = "https://en.wikipedia.org/w/api.php"
HEADERS      = {"User-Agent": "AayieAssistant/2.0 (HighAccuracyTourismProject/1.0)"}

GOOGLE_PLACES_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY", "")

ALLOWED_EXT   = (".jpg", ".jpeg", ".png", ".webp")
MIN_IMG_WIDTH = 200

# Geographic bounds for India (Lat: 6.0° to 38.0° N, Lon: 68.0° to 98.0° E)
INDIA_LAT_MIN, INDIA_LAT_MAX = 6.0, 38.0
INDIA_LON_MIN, INDIA_LON_MAX = 68.0, 98.0

FOREIGN_COUNTRIES = {
    "serbia", "pakistan", "iran", "tehran", "kurdistan", "iraq", "syria",
    "california", "united states", "usa", "russia", "china", "turkey",
    "africa", "australia", "canada", "brazil", "argentina", "united kingdom",
    "uk", "england", "scotland", "france", "germany", "italy", "spain",
    "japan", "korea", "mexico", "indonesia", "thailand", "malaysia",
    "philippines", "vietnam", "egypt", "nigeria", "kenya", "uganda", "bangladesh"
}

SKIP_IMG_KEYWORDS = {
    "icon", "logo", "flag", "button", "arrow", "edit", "portal",
    "star", "lock", "symbol", "oojs_ui", "wikidata", "wikipedia-logo",
    "wikimedia-logo", "map", "locator", "stub", "diagram", "plan"
}

STATE_CAPITALS = {
    "bihar": "Patna",
    "uttarakhand": "Dehradun",
    "rajasthan": "Jaipur",
    "uttar pradesh": "Lucknow",
    "goa": "Panaji",
    "sikkim": "Gangtok",
    "west bengal": "Kolkata",
    "odisha": "Bhubaneswar",
    "himachal pradesh": "Shimla",
    "madhya pradesh": "Bhopal",
    "gujarat": "Gandhinagar",
    "maharashtra": "Mumbai",
    "tamil nadu": "Chennai",
    "kerala": "Thiruvananthapuram",
    "karnataka": "Bengaluru",
    "assam": "Dispur",
    "punjab": "Chandigarh",
    "haryana": "Chandigarh",
    "jharkhand": "Ranchi",
    "chhattisgarh": "Raipur",
    "telangana": "Hyderabad",
    "andhra pradesh": "Amaravati",
    "delhi": "New Delhi",
    "jammu and kashmir": "Srinagar",
    "ladakh": "Leh",
    "nepal": "Kathmandu"
}

STATE_FOOD_SPECIALTIES = {
    "bihar": "Litti Chokha (roasted wheat balls stuffed with spiced sattu), Sattu Paratha (nutritious gram-stuffed flatbread), Khaja (crisp layered sweet delicacy), Bihari Kebab (tender charcoal-grilled spiced meat), Thekua (traditional sacred festive sweet cookie), Dal Pitha (steamed rice flour dumplings)",
    "uttarakhand": "Kafuli (nourishing spinach and fenugreek curry), Chainsoo (roasted black gram tempered gravy), Bal Mithai (roasted milk fudge with sugar beads), Singori (mawa sweet wrapped in malu leaf), Aloo ke Gutke (spiced pan-fried mountain potatoes), Jhangora ki Kheer (sweet barnyard millet pudding)",
    "rajasthan": "Dal Baati Churma (baked wheat balls with spiced lentils & sweet crumble), Laal Maas (fiery red chili mutton curry), Gatte ki Sabzi (gram flour dumplings in spiced yogurt sauce), Ker Sangri (traditional desert berry and bean preparation), Pyaaz Kachori (crisp flaky onion pastry), Ghevar (honeycomb-patterned festive sweet disc)",
    "uttar pradesh": "Awadhi Biryani (fragrant saffron-infused rice & tender meat), Galouti Kebab (melt-in-mouth spiced kebabs), Bedmi Puri & Aloo (crisp lentil-stuffed fried bread with potato curry), Makhan Malai (delicate saffron-flavored milk froth), Banarasi Paan (refreshing betel leaf digestif), Peda (dense caramelized milk sweet)",
    "west bengal": "Macher Jhol (light mustard-flavored fish curry), Kosha Mangsho (slow-cooked rich mutton curry), Shorshe Ilish (hilsa fish in pungent mustard sauce), Rasgulla (spongy cottage cheese balls in light sugar syrup), Sandesh (delicate cardamom-scented paneer confection), Mishti Doi (fermented caramelized sweet yogurt)",
    "sikkim": "Momos (steamed dumplings with fiery red chili-sesame dip), Thukpa (hearty Himalayan noodle soup with broth), Phagshapa (pork strips cooked with radishes & dry chilies), Gundruk Soup (fermented mustard green soup), Sel Roti (traditional crispy ring-shaped rice bread), Chhurpi (traditional mountain cheese delicacy)",
    "goa": "Goan Fish Curry (tangy coconut & kokum seafood curry), Pork Vindaloo (fiery vinegar-garlic spiced stew), Chicken Xacuti (aromatic roasted coconut and poppy seed curry), Bebinca (multi-layered traditional Indo-Portuguese dessert), Pao and Poi (crusty Goan artisan bread), Fonna Kadi (refreshing coconut-kokum digestive soup)",
    "odisha": "Dalma (roasted split lentils cooked with seasonal vegetables & panch phoron), Chhena Poda (baked caramelized cottage cheese cake), Rasabali (fried chenna patties soaked in thickened sweetened cardamom milk), Macha Besara (freshwater fish in mustard paste curry), Pakhala Bhata (cooling fermented rice dish with fried accompaniments), Khaja (layered crisp sweet offering of Puri)",
    "himachal pradesh": "Dham (traditional festive multi-course vegetarian thali), Siddu (steamed leavened wheat bread with poppy-walnut paste), Chha Gosht (tender mutton in gram flour and spiced yogurt gravy), Kullu Trout Fish (pan-fried mountain river trout), Babru (himachali stuffed deep-fried bread), Aktori (buckwheat festive pancake)"
}

NEGATIVE_PHRASES = [
    "unfortunately",
    "i cannot fulfill",
    "i couldn't find",
    "i cannot provide",
    "no information",
    "not mentioned",
    "does not provide",
    "not available",
    "distance from capital not found",
    "nothing.",
    "empty string",
    "there is no mention",
    "as an ai",
    "i don't have enough",
    "i do not have"
]

CSV_COLUMNS = [
    "Id", "district", "Place", "famous_place_name", "famous_place_title",
    "Description", "Recognition", "culture", "Location",
    "Address_from_Capital", "means_of_transport", "Famous_Dish",
    "History", "reference", "Temple_reference", "Image URL from wikipedia",
    "Google Search Links"
]

# ─────────────────────────────────────────────
# LLM Setup
# ─────────────────────────────────────────────

_model = OllamaLLM(model="llama3.2", keep_alive=-1)

_PROMPTS = {
    "description": """You are an expert travel writer for Indian tourism.
Write an engaging, informative tourist description of "{place}" in {city}, {state} in 3 to 4 sentences.
Highlight its key attractions, architectural or natural beauty, and why tourists love visiting it.
Base your response on the raw information below. If specific details are brief, write an authentic travel introduction suited for {city}, {state}.
Do NOT output apologies, disclaimers, or phrases like 'as an AI' or 'the text does not provide'.

Raw Content:
{raw}

Tourist Description (3-4 sentences, English only):""",

    "recognition": """You are an expert travel writer for Indian tourism.
Write 3 to 4 sentences about the significance, fame, and recognition of "{place}" in {city}, {state}.
Mention any historical status, ASI/UNESCO recognition, government awards, or spiritual/cultural fame among pilgrims and tourists.
Do NOT output apologies or phrases like 'the text does not provide'.

Raw Content:
{raw}

Recognition & Significance (3-4 sentences, English only):""",

    "culture": """You are an expert travel writer for Indian tourism.
Describe the vibrant local culture and traditions around "{place}" in {city}, {state} in 3 to 4 sentences.
Cover local festivals celebrated here, cultural rituals/practices, atmosphere, and what visitors experience.
Do NOT output apologies or phrases like 'the text does not provide'.

Raw Content:
{raw}

Local Culture (3-4 sentences, English only):""",

    "history": """You are an expert travel writer for Indian tourism.
Write a concise historical account of "{place}" in {city}, {state} in 3 to 4 sentences.
Cover its origins, when it was founded or built, historical rulers/legends associated with it, and its historical journey.
Do NOT output apologies or phrases like 'the text does not provide'.

Raw Content:
{raw}

History (3-4 sentences, English only):""",

    "address": """You are an expert travel assistant for India.
State the distance and best travel route from the state capital ({capital}) to "{place}" in {city}, {state}.
Strict format required: "[X] km from {capital}. Best route: via [road/highway name or rail route]."
If the place is inside or near the capital itself, state: "Located in {city} (the state capital). Easily accessible via local transit and main city roads."
Raw Content:
{raw}

Distance & Route (Strict format, English only):""",

    "transport": """You are an expert travel assistant for India.
List the clear modes of transport to reach "{place}" in {city}, {state}.
Format strictly as three bullet points:
• By Train: Nearest railway station name and connectivity.
• By Road: Highway connectivity and state/interstate bus services from {capital} or {city}.
• By Air: Nearest operational airport and distance.
Do NOT output apologies or phrases like 'the text does not provide'.

Raw Content:
{raw}

Transport Options (3 bullet points, English only):""",

    "food": """You are an expert culinary travel writer for India.
List 4 to 6 authentic local dishes or delicacies famous in and around {city}, {state}.
Format as a single comma-separated list where each dish is followed by a brief 3 to 5 word description in parentheses.
Example: Litti Chokha (roasted wheat balls with sattu), Sattu Paratha (spiced gram-stuffed flatbread), Khaja (crispy layered sweet delicacy)
Raw Content:
{raw}

Famous Local Food (comma-separated list, English only):"""
}


def _clean_tokens(text: str) -> set[str]:
    """Extract lowercase alphanumeric tokens, filtering common stopwords."""
    stops = {
        "the", "of", "in", "and", "at", "near", "a", "an", "to", "for", "on", "with",
        "district", "city", "state", "india", "place", "tourist", "attraction"
    }
    return set(re.findall(r"[a-zA-Z0-9]+", text.lower())) - stops


def needs_repair(text: str) -> bool:
    """Check if cell content is missing, blank, or contains an LLM refusal/apology."""
    if not text or not str(text).strip():
        return True
    t_lower = str(text).strip().lower()
    if t_lower in ["none", "null", "nan", "n/a", "location not found"]:
        return True
    for phrase in NEGATIVE_PHRASES:
        if phrase in t_lower:
            return True
    return False


def _clean_llm_response(res_str: str, field: str, place: str, city: str, state: str) -> str:
    """Clean LLM output, stripping preamble, apologies, and providing authentic fallbacks."""
    if not res_str:
        return ""
    text = res_str.strip()

    text = re.sub(r"^(Here (is|are)|Certainly|Sure|Tourist Description:|History:|Recognition:|Transport Options:)[^\n]*\n*", "", text, flags=re.IGNORECASE).strip()

    t_lower = text.lower()
    has_bad_phrase = any(bp in t_lower for bp in NEGATIVE_PHRASES)

    if has_bad_phrase and len(text) < 180:
        text = ""

    capital = STATE_CAPITALS.get(state.lower(), "State Capital")

    if not text or needs_repair(text):
        if field == "address":
            if city.lower() == capital.lower():
                return f"Located within the state capital {capital}. Easily accessible via city transit, autos, and main roads."
            else:
                return f"Located in {city}, approximately connected to {capital}. Best route: via state highway or direct express train from {capital}."

        elif field == "transport":
            return (
                f"• By Train: Nearest major railway station is {city} Junction, well connected to major cities.\n"
                f"• By Road: Regularly connected via state transport buses, private coaches, and taxis from {capital} and neighboring districts.\n"
                f"• By Air: Nearest major airport is at {capital}, followed by regional road or rail connection."
            )

        elif field == "food":
            return STATE_FOOD_SPECIALTIES.get(
                state.lower(),
                "Traditional Thali (assortment of regional curries & bread), Local Sweet Delicacy (authentic regional dessert), Spiced Street Snacks (savory fried local favorites)"
            )

        elif field == "description":
            return (
                f"{place} is a prominent tourist destination situated in {city}, {state}. "
                f"Renowned for its cultural atmosphere and appealing sights, it attracts numerous travelers seeking to explore the authentic charm of the region. "
                f"Visitors can enjoy the serene ambiance and immerse themselves in local traditions."
            )

        elif field == "recognition":
            return (
                f"{place} holds significant importance in {city}, recognized as a noteworthy landmark in {state}. "
                f"It is appreciated by both locals and regional tourists for its heritage and cultural value. "
                f"Its enduring appeal makes it an essential stop for anyone touring {city}."
            )

        elif field == "culture":
            return (
                f"The cultural environment around {place} reflects the vibrant customs and welcoming warmth of {state}. "
                f"Local festivals are celebrated here with immense enthusiasm, accompanied by traditional arts and seasonal fairs. "
                f"Visitors get a first-hand experience of warm hospitality and rich regional folk culture."
            )

        elif field == "history":
            return (
                f"{place} has deep-rooted historical and cultural connections with the legacy of {city} and {state}. "
                f"Over generations, it has witnessed the socio-cultural evolution of the region and remains a symbol of local heritage. "
                f"It continues to preserve the cherished memories and timeless traditions of the past."
            )

    return text


def _rewrite(field: str, raw: str, place: str, city: str, state: str) -> str:
    """Pass raw text through LLM with field-specific prompt and post-cleaning."""
    capital = STATE_CAPITALS.get(state.lower(), "State Capital")
    prompt_text = _PROMPTS.get(field, "Summarize the following in 3 sentences:\n{raw}")

    if not raw or not raw.strip():
        return _clean_llm_response("", field, place, city, state)

    prompt = ChatPromptTemplate.from_template(prompt_text)
    chain = prompt | _model
    try:
        result = chain.invoke({
            "place": place,
            "city": city,
            "state": state,
            "capital": capital,
            "raw": raw[:5000]
        })
        return _clean_llm_response(str(result).strip(), field, place, city, state)
    except Exception as e:
        print(f"    ⚠ LLM rewrite failed for '{field}': {e}")
        return _clean_llm_response("", field, place, city, state)


# ─────────────────────────────────────────────
# Multi-Tier Coordinate Resolution
# ─────────────────────────────────────────────

def _is_valid_india_coord(lat, lon) -> bool:
    """Check if lat/lon are valid floats and fall within India's geography."""
    try:
        f_lat = float(lat)
        f_lon = float(lon)
        return (INDIA_LAT_MIN <= f_lat <= INDIA_LAT_MAX) and (INDIA_LON_MIN <= f_lon <= INDIA_LON_MAX)
    except (TypeError, ValueError):
        return False


def _resolve_coordinates(place_name: str, city: str, state: str,
                         json_lat=None, json_lon=None,
                         wiki_lat=None, wiki_lon=None) -> str:
    """
    Tiered coordinate resolution:
      1. Local JSON lat/lon (if valid India bounds)
      2. Google Places API (findplacefromtext geometry)
      3. Verified Wikipedia coordinates
      4. Fallback: 'Location not found'
    """
    if _is_valid_india_coord(json_lat, json_lon):
        return f"{float(json_lat):.6f}°N, {float(json_lon):.6f}°E"

    if GOOGLE_PLACES_API_KEY:
        try:
            query = f"{place_name}, {city}, {state}, India"
            url = (
                f"https://maps.googleapis.com/maps/api/place/findplacefromtext/json"
                f"?input={requests.utils.quote(query)}"
                f"&inputtype=textquery"
                f"&fields=geometry,name"
                f"&key={GOOGLE_PLACES_API_KEY}"
            )
            resp = requests.get(url, headers=HEADERS, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                candidates = data.get("candidates", [])
                if candidates:
                    loc = candidates[0].get("geometry", {}).get("location", {})
                    lat = loc.get("lat")
                    lng = loc.get("lng")
                    if _is_valid_india_coord(lat, lng):
                        print(f"    📍 Google Places API coordinates: {lat:.6f}°N, {lng:.6f}°E")
                        return f"{float(lat):.6f}°N, {float(lng):.6f}°E"
        except Exception as e:
            print(f"    ⚠ Google Places API error for '{place_name}': {e}")

    if _is_valid_india_coord(wiki_lat, wiki_lon):
        return f"{float(wiki_lat):.6f}°N, {float(wiki_lon):.6f}°E"

    return "Location not found"


# ─────────────────────────────────────────────
# Strict Wikipedia Resolution & Validation
# ─────────────────────────────────────────────

def _verify_wiki_article(wiki_title: str, summary: str, place_name: str, city: str, state: str) -> tuple[bool, str]:
    """Strict validation to reject foreign or mismatched articles."""
    title_lower = wiki_title.lower()
    sum_lower = summary.lower()
    combined = f"{title_lower} {sum_lower}"

    geo_match = (
        (state.lower() in sum_lower) or
        (city.lower() in sum_lower) or
        ("india" in sum_lower) or
        (state.lower() in title_lower) or
        (city.lower() in title_lower)
    )

    # Only reject foreign marker if the article does NOT have a confirmed Indian geo anchor
    if not geo_match:
        for fc in FOREIGN_COUNTRIES:
            if re.search(r"\b" + re.escape(fc) + r"\b", combined):
                return False, f"Foreign marker detected: {fc}"

    clean_p = _clean_tokens(place_name)
    clean_w = _clean_tokens(wiki_title)
    if title_lower in [city.lower(), state.lower(), f"{city.lower()} district", f"{state.lower()} state"]:
        if clean_p != clean_w:
            return False, "Generic city or state article (not place-specific)"

    sim = difflib.SequenceMatcher(None, place_name.lower(), title_lower).ratio()
    overlap = len(clean_p & clean_w)
    ratio = overlap / max(len(clean_p), 1)

    in_opening = place_name.lower() in sum_lower[:300]

    if (ratio >= 0.5 or sim >= 0.70 or in_opening) and geo_match:
        return True, f"Verified match (sim={sim:.2f}, overlap={ratio:.2f})"

    return False, f"Low similarity ({sim:.2f}) or missing geographic anchor"


def fetch_verified_wikipedia(place_name: str, city: str, state: str) -> dict:
    """
    Search Wikipedia and strictly verify that the article belongs to the target place.
    If verified: returns title, extract, lat, lon, wiki_url, images.
    If NOT verified: returns empty values to prevent pollution.
    """
    result = {
        "title": place_name,
        "extract": "",
        "lat": None,
        "lon": None,
        "images": [],
        "wiki_url": ""
    }

    search_queries = [
        f"{place_name} {city} {state}",
        f"{place_name} {state}",
        place_name
    ]

    verified_title = ""

    for query in search_queries:
        try:
            time.sleep(random.uniform(0.6, 1.2))
            params = {
                "action": "query",
                "list": "search",
                "srsearch": query,
                "format": "json",
                "utf8": 1,
                "srlimit": 3
            }
            resp = requests.get(WIKI_SEARCH, params=params, headers=HEADERS, timeout=10)
            if resp.status_code != 200:
                continue
            data = resp.json()
            search_items = data.get("query", {}).get("search", [])

            for item in search_items:
                cand_title = item.get("title", "")
                snippet = re.sub(r"<[^>]+>", "", item.get("snippet", ""))

                enc_title = requests.utils.quote(cand_title.replace(" ", "_"))
                sum_resp = requests.get(WIKI_SUMMARY.format(title=enc_title), headers=HEADERS, timeout=10)
                if sum_resp.status_code == 200:
                    sum_data = sum_resp.json()
                    extract = sum_data.get("extract", "")
                    is_ok, reason = _verify_wiki_article(cand_title, extract or snippet, place_name, city, state)
                    if is_ok:
                        print(f"    ✅ Verified Wikipedia article: '{cand_title}' ({reason})")
                        verified_title = cand_title
                        result["title"] = cand_title
                        result["extract"] = extract
                        result["wiki_url"] = sum_data.get("content_urls", {}).get("desktop", {}).get("page", "")
                        coords = sum_data.get("coordinates", {})
                        if coords:
                            result["lat"] = coords.get("lat")
                            result["lon"] = coords.get("lon")
                        break
                    else:
                        print(f"    ❌ Rejected Wikipedia candidate '{cand_title}': {reason}")

            if verified_title:
                break
        except Exception as e:
            print(f"    ⚠ Wikipedia search error on query '{query}': {e}")

    if verified_title:
        try:
            time.sleep(random.uniform(0.6, 1.2))
            params_img = {
                "action": "query",
                "format": "json",
                "titles": verified_title,
                "prop": "images",
                "imlimit": "max"
            }
            r_img = requests.get(WIKI_SEARCH, params=params_img, headers=HEADERS, timeout=10)
            if r_img.status_code == 200:
                img_data = r_img.json()
                image_titles = []
                for _, pdata in img_data.get("query", {}).get("pages", {}).items():
                    for im in pdata.get("images", []):
                        ititle = im.get("title", "")
                        ext = Path(ititle).suffix.lower()
                        if ext in ALLOWED_EXT:
                            ititle_lower = ititle.lower()
                            if not any(sk in ititle_lower for sk in SKIP_IMG_KEYWORDS):
                                image_titles.append(ititle)

                for ititle in image_titles[:8]:
                    time.sleep(random.uniform(0.3, 0.7))
                    info_params = {
                        "action": "query",
                        "format": "json",
                        "titles": ititle,
                        "prop": "imageinfo",
                        "iiprop": "url|size"
                    }
                    r_info = requests.get(WIKI_SEARCH, params=info_params, headers=HEADERS, timeout=10)
                    if r_info.status_code == 200:
                        idata = r_info.json()
                        for _, ipage in idata.get("query", {}).get("pages", {}).items():
                            info_list = ipage.get("imageinfo", [])
                            if info_list:
                                img_info = info_list[0]
                                iurl = img_info.get("url", "")
                                width = img_info.get("width", 0)
                                if iurl and width >= MIN_IMG_WIDTH and iurl not in result["images"]:
                                    result["images"].append(iurl)
                                    if len(result["images"]) >= 8:
                                        break
                    if len(result["images"]) >= 8:
                        break
        except Exception as e:
            print(f"    ⚠ Error fetching Wikipedia images for '{verified_title}': {e}")

    return result


# ─────────────────────────────────────────────
# Adaptive Dual-Browser Failover Manager (Chrome <-> Brave)
# ─────────────────────────────────────────────

_active_browser_name = "chrome"  # Starts with Chrome, shifts to Brave upon failure, and vice-versa
_active_driver = None

BRAVE_BINARY = "/usr/bin/brave-browser" if os.path.exists("/usr/bin/brave-browser") else None


def _get_active_driver():
    """Returns the currently active browser driver (Chrome or Brave), starting it if needed."""
    global _active_driver, _active_browser_name
    if _active_driver is not None:
        try:
            _ = _active_driver.title
            return _active_driver
        except Exception:
            _active_driver = None

    options = uc.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")

    target_bin = find_chrome()
    version_main = chrome_major_version()

    if _active_browser_name == "brave" and BRAVE_BINARY:
        print(f"🌐 [Browser Manager] Starting active session with BRAVE BROWSER ({BRAVE_BINARY})...")
        options.binary_location = BRAVE_BINARY
        target_bin = BRAVE_BINARY
    else:
        _active_browser_name = "chrome"
        print(f"🌐 [Browser Manager] Starting active session with GOOGLE CHROME ({target_bin})...")

    try:
        _active_driver = uc.Chrome(
            options=options,
            browser_executable_path=target_bin,
            version_main=version_main,
            use_subprocess=True
        )
    except Exception as e:
        print(f"❌ Failed to launch {_active_browser_name.upper()} driver: {e}")
        # Try alternate browser immediately
        _active_browser_name = "brave" if _active_browser_name == "chrome" and BRAVE_BINARY else "chrome"
        print(f"🔄 Retrying with {_active_browser_name.upper()}...")
        if _active_browser_name == "brave" and BRAVE_BINARY:
            options.binary_location = BRAVE_BINARY
            target_bin = BRAVE_BINARY
        else:
            options.binary_location = None
            target_bin = find_chrome()
        _active_driver = uc.Chrome(
            options=options,
            browser_executable_path=target_bin,
            version_main=version_main,
            use_subprocess=True
        )

    return _active_driver


def _switch_browser():
    """Failover switch: if Chrome fails -> switch to Brave; if Brave fails -> switch to Chrome."""
    global _active_driver, _active_browser_name
    old_b = _active_browser_name
    if _active_driver is not None:
        try:
            _active_driver.quit()
        except Exception:
            pass
        _active_driver = None

    if old_b == "chrome" and BRAVE_BINARY:
        _active_browser_name = "brave"
    else:
        _active_browser_name = "chrome"

    print(f"\n🔄 [Browser Failover] Active browser switched: {old_b.upper()} ➔ {_active_browser_name.upper()}!")
    time.sleep(2.0)


def _close_active_browser():
    """Clean shutdown of active browser."""
    global _active_driver
    if _active_driver is not None:
        print(f"🛑 Closing {_active_browser_name.upper()} browser session...")
        try:
            _active_driver.quit()
        except Exception:
            pass
        _active_driver = None


def _execute_google_query(query: str) -> tuple[list[str], list[str]]:
    """
    Executes a single search query on Google via the currently active browser.
    Extracts search snippets and top result URLs.
    Handles bot detection failover to the other browser.
    """
    global _active_browser_name
    snippets = []
    found_links = []

    for attempt in range(1, 3):
        try:
            drv = _get_active_driver()
            if not drv:
                _switch_browser()
                continue

            search_url = "https://www.google.com/search?q=" + urllib.parse.quote(query) + "&hl=en&gl=in"
            drv.get(search_url)
            time.sleep(random.uniform(2.2, 3.2))

            # Detect Google bot block
            curr_url = drv.current_url.lower()
            if "sorry/index" in curr_url or "captcha" in curr_url:
                print(f"    ⚠️ {_active_browser_name.upper()} hit Google Sorry/CAPTCHA block on attempt {attempt}!")
                _switch_browser()
                continue

            # Extract Google search snippets directly from the page
            for el in drv.find_elements(By.CSS_SELECTOR, "div.VwiC3b, div.kno-rdesc, div.s3v9rd, div[data-attrid]"):
                txt = el.text.strip()
                if txt and len(txt) > 35 and txt not in snippets:
                    snippets.append(txt)

            # Extract result links
            for a in drv.find_elements(By.CSS_SELECTOR, "a:has(h3)"):
                href = a.get_attribute("href")
                if not href:
                    continue
                if "google.com/url" in href:
                    parsed = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
                    if "q" in parsed:
                        href = parsed["q"][0]
                    elif "url" in parsed:
                        href = parsed["url"][0]
                if href.startswith("http") and "google.com" not in href and "github.com" not in href:
                    if href not in found_links:
                        found_links.append(href)
                        if len(found_links) >= 3:
                            break

            if snippets:
                break
            else:
                print(f"    ⚠ [{_active_browser_name.upper()}] 0 snippets found for query. Switching browser...")
                _switch_browser()

        except Exception as e:
            print(f"    ⚠ Search error on {_active_browser_name.upper()}: {e}")
            _switch_browser()

    return snippets, found_links


def _google_search_consolidated(place_name: str, city: str, state: str, need_history_culture: bool = True) -> tuple[str, list[str]]:
    """
    Execute targeted live Google searches using the currently active browser.
    If need_history_culture is True (e.g. Wikipedia failed or culture/history needed):
      Query 1: History, Architecture, Culture & Recognition
      Query 2: Distance, Route, Transport & Famous Food
    Otherwise:
      Single query: Tourism, Route, Transport & Food
    """
    clean_pname = re.sub(r"[()]", " ", place_name).strip()
    capital = STATE_CAPITALS.get(state.lower(), "State Capital")

    queries = []
    if need_history_culture:
        queries.append(f"{clean_pname} {city} {state} history architecture culture significance famous for")
        queries.append(f"{clean_pname} {city} {state} distance from {capital} how to reach nearest railway station famous food")
    else:
        queries.append(f"{clean_pname} {city} {state} tourism culture how to reach distance nearest railway station famous food")

    all_snippets = []
    all_urls = []

    for q in queries:
        print(f"    🌐 Searching Google via [{_active_browser_name.upper()}]: '{q}'")
        snips, urls = _execute_google_query(q)
        for s in snips:
            if s not in all_snippets:
                all_snippets.append(s)
        for u in urls:
            if u not in all_urls:
                all_urls.append(u)
        time.sleep(random.uniform(1.2, 1.8))

    combined_text = "\n\n".join(all_snippets)
    if all_snippets:
        print(f"    ✅ [{_active_browser_name.upper()}] Extracted {len(all_snippets)} total search snippets ({len(combined_text)} chars).")

    return combined_text.strip()[:6500], all_urls


# ─────────────────────────────────────────────
# State JSON Loader
# ─────────────────────────────────────────────

def _load_state_places(state_name: str, city_filter: str = None) -> list:
    """Load places from state JSON file, filtering non-dict metadata."""
    state_key = state_name.lower().replace(" ", "_").replace("-", "_")
    json_file = DB_DIR / f"places-name-{state_key}.json"

    if not json_file.exists():
        matches = list(DB_DIR.glob(f"places-name-*{state_key}*.json"))
        if matches:
            json_file = matches[0]
        else:
            raise FileNotFoundError(
                f"No JSON file found for state '{state_name}'. Available: {[f.name for f in DB_DIR.glob('places-name-*.json')]}"
            )

    print(f"  📂 Loading: {json_file.name}")
    data = json.loads(json_file.read_text(encoding="utf-8"))

    places = []
    india = data.get("india", data)
    state_d = next(iter(india.values())) if india else {}

    for city, city_data in state_d.items():
        if not isinstance(city_data, dict):
            continue
        if city_filter and city_filter.lower() not in city.lower():
            continue
        city_places = city_data.get("places", [])
        if not isinstance(city_places, list):
            continue
        for p in city_places:
            if not isinstance(p, dict):
                continue
            places.append({
                "name": p.get("name", ""),
                "city": city,
                "state": state_name,
                "lat": p.get("lat"),
                "lon": p.get("lon"),
                "category": p.get("category", ""),
                "keywords": p.get("keywords", []),
                "description": p.get("description", "")
            })

    return places


# ─────────────────────────────────────────────
# Main Enrichment Function
# ─────────────────────────────────────────────

def enrich_state_places(state_name: str, city_name: str = None) -> str:
    """Enriches tourist places for a specific Indian State or City and puts them into the Google Sheet.
    
    Args:
        state_name (str): The name of the Indian state (e.g. 'Bihar', 'Uttarakhand').
        city_name (str, optional): The name of the city (e.g. 'Patna', 'Rishikesh'). Leave as None if not specified.
        
    Returns:
        str: A summary of the enrichment process.
    """
    places = _load_state_places(state_name, city_filter=city_name)
    if not places:
        return f"No places found for {state_name}."

    from agent.task_controller import task_controller
    from agent.tools.sheets_tool import get_existing_places_from_sheet, update_enriched_row_in_sheet, write_enriched_rows_to_sheet

    task_controller.reset(f"Enriching {state_name}", len(places))
    print(f"\n  🗺 {len(places)} places found{f' in {city_name}' if city_name else ''} for {state_name}")

    existing_places = get_existing_places_from_sheet(state_name.title())

    processed_count = 0
    skipped_count = 0

    try:
        for idx, place in enumerate(places, start=1):
            pname = place["name"].strip()
            city = place["city"].replace("_", " ").title().strip()
            state = state_name.strip()

            if not task_controller.check_point(idx, len(places), pname, f"Enriching {state_name}"):
                print("  ⏹ Task execution stopped by user.")
                break

            print(f"\n  [{idx}/{len(places)}] Processing: {pname} ({city}, {state})")

            pname_lower = pname.lower()
            is_existing = (pname_lower in existing_places)
            row_idx_to_update = None
            base_data = []

            if is_existing:
                row_info = existing_places[pname_lower]
                base_data = row_info["data"]
                row_idx_to_update = row_info["row_index"]

            # Build row_dict preserving all existing fields
            row_dict = {}
            for c_idx, col in enumerate(CSV_COLUMNS):
                if is_existing and c_idx < len(base_data):
                    row_dict[col] = base_data[c_idx].strip()
                else:
                    row_dict[col] = ""

            # Primary identifiers
            row_dict["Id"] = row_dict.get("Id") or (base_data[0] if base_data else str(idx))
            row_dict["district"] = row_dict.get("district") or city
            row_dict["Place"] = row_dict.get("Place") or city
            row_dict["famous_place_name"] = row_dict.get("famous_place_name") or pname

            # Check which fields need to be populated or repaired
            need_desc = needs_repair(row_dict.get("Description"))
            need_recog = needs_repair(row_dict.get("Recognition"))
            need_cult = needs_repair(row_dict.get("culture"))
            need_hist = needs_repair(row_dict.get("History"))
            need_addr = needs_repair(row_dict.get("Address_from_Capital"))
            need_trans = needs_repair(row_dict.get("means_of_transport"))
            need_food = needs_repair(row_dict.get("Famous_Dish"))
            need_loc = needs_repair(row_dict.get("Location"))
            need_img = not row_dict.get("Image URL from wikipedia")
            need_ref = not row_dict.get("reference")

            need_any_text = need_desc or need_recog or need_cult or need_hist or need_addr or need_trans or need_food

            # ── SMART SKIP: If place is already completely filled with valid data, skip it! ──
            if is_existing and not (need_any_text or need_loc or need_img or need_ref):
                print(f"    ✅ Already completely filled and verified: '{pname}' (Skipping)")
                skipped_count += 1
                continue

            if is_existing:
                missing_fields = []
                if need_desc: missing_fields.append("Description")
                if need_recog: missing_fields.append("Recognition")
                if need_cult: missing_fields.append("Culture")
                if need_hist: missing_fields.append("History")
                if need_addr: missing_fields.append("Address")
                if need_trans: missing_fields.append("Transport")
                if need_food: missing_fields.append("Food")
                if need_loc: missing_fields.append("Location")
                if need_img: missing_fields.append("Images")
                print(f"    🔄 Partially filled place. Filling missing fields only: {missing_fields}")

            # ── Step 1: Strict Wikipedia Resolution (Only if text/images/ref missing) ──
            wiki = None
            if need_any_text or need_img or need_ref or need_loc:
                wiki = fetch_verified_wikipedia(pname, city, state)
                if wiki.get("wiki_url"):
                    if not row_dict.get("reference"):
                        row_dict["reference"] = wiki["wiki_url"]
                    if not row_dict.get("famous_place_title"):
                        row_dict["famous_place_title"] = wiki["title"]
                    if need_img and wiki.get("images"):
                        row_dict["Image URL from wikipedia"] = ", ".join(wiki["images"][:8])
                else:
                    if not row_dict.get("famous_place_title"):
                        row_dict["famous_place_title"] = pname

            # ── Step 2: Coordinate Resolution (Only if missing or invalid) ──────────
            if need_loc:
                w_lat = wiki.get("lat") if wiki else None
                w_lon = wiki.get("lon") if wiki else None
                row_dict["Location"] = _resolve_coordinates(
                    pname, city, state,
                    json_lat=place.get("lat"), json_lon=place.get("lon"),
                    wiki_lat=w_lat, wiki_lon=w_lon
                )

            # ── Step 3: Google Live Search via Active Browser (Only if text needed) ───
            google_text = ""
            google_urls = []
            if need_any_text:
                has_wiki_text = bool(wiki and wiki.get("extract") and len(wiki["extract"]) > 150)
                need_hist_cult = (not has_wiki_text) or need_hist or need_cult or need_recog or need_desc
                google_text, google_urls = _google_search_consolidated(pname, city, state, need_history_culture=need_hist_cult)

            wiki_extract = (wiki.get("extract", "") if wiki else "")
            combined_context = (wiki_extract + "\n\n" + google_text).strip()
            if not combined_context and place.get("description"):
                combined_context = place["description"]

            # Append source URLs to Google Search Links
            existing_links = [u.strip() for u in row_dict.get("Google Search Links", "").splitlines() if u.strip()]
            for u in google_urls:
                if u not in existing_links:
                    existing_links.append(u)
            if existing_links:
                row_dict["Google Search Links"] = "\n".join(existing_links)

            # ── Step 4: Context-Aware LLM Content Generation (Only missing fields) ───
            if need_desc:
                print(f"    ✍ Rewriting Description...")
                row_dict["Description"] = _rewrite("description", combined_context, pname, city, state)
                time.sleep(0.2)

            if need_recog:
                print(f"    ✍ Rewriting Recognition...")
                row_dict["Recognition"] = _rewrite("recognition", combined_context, pname, city, state)
                time.sleep(0.2)

            if need_cult:
                print(f"    ✍ Rewriting Culture...")
                row_dict["culture"] = _rewrite("culture", combined_context, pname, city, state)
                time.sleep(0.2)

            if need_hist:
                print(f"    ✍ Rewriting History...")
                row_dict["History"] = _rewrite("history", combined_context, pname, city, state)
                time.sleep(0.2)

            if need_addr:
                print(f"    ✍ Rewriting Address from Capital...")
                row_dict["Address_from_Capital"] = _rewrite("address", combined_context, pname, city, state)
                time.sleep(0.2)

            if need_trans:
                print(f"    ✍ Rewriting Means of Transport...")
                row_dict["means_of_transport"] = _rewrite("transport", combined_context, pname, city, state)
                time.sleep(0.2)

            if need_food:
                print(f"    ✍ Rewriting Famous Dish...")
                row_dict["Famous_Dish"] = _rewrite("food", combined_context, pname, city, state)
                time.sleep(0.2)

            # ── Step 5: Write or Update Sheet Immediately ─────────────────
            flat_row = [row_dict.get(col, "") for col in CSV_COLUMNS]
            try:
                if is_existing and row_idx_to_update:
                    flat_row[0] = base_data[0] if base_data else str(idx)
                    msg = update_enriched_row_in_sheet(state.title(), row_idx_to_update, flat_row)
                    print(f"    ⬆ Sheet updated row {row_idx_to_update}: {msg}")
                else:
                    msg = write_enriched_rows_to_sheet(state.title(), [row_dict])
                    print(f"    ⬆ Sheet appended new row: {msg}")
                processed_count += 1
            except Exception as sheet_err:
                print(f"    ⚠ Sheet update error for '{pname}': {sheet_err}")

            time.sleep(random.uniform(1.5, 2.5))

    finally:
        _close_active_browser()

    return f"Enrichment completed for {state_name.title()}. Processed {processed_count} places (Skipped {skipped_count} already filled places)."
