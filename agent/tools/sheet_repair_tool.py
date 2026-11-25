"""
agent/tools/sheet_repair_tool.py

High-accuracy spreadsheet audit and repair tool for Indian tourist places.
Scans Google Sheets for a given state (and optional city) to detect and repair:
  1. Negative or apologetic LLM responses ("Unfortunately...", "Nothing.", "Distance from capital not found.")
  2. Missing, blank, or invalid coordinates (e.g. foreign coordinates outside India)
  3. Mismatched or foreign Wikipedia links and images (e.g. Serbian towns, Pakistani dancers, Iranian parks)
  4. Missing transport bullet points, authentic food items, or tourist descriptions

Executes:
  - Multi-tier coordinate re-resolution (JSON -> Google Places API -> Verified Wikipedia)
  - Strict Wikipedia re-verification (clearing foreign pollution and restoring authentic Wikimedia images)
  - Consolidated Google Live Search (1 combined search per place, session refresh, zero 3rd-party fallbacks)
  - LLM rewriting with rigorous post-cleaning and authentic regional fallbacks
  - Direct in-place Google Sheets row updates preserving original IDs
"""

import re
import json
import time
import random
import socket
from pathlib import Path

# Force IPv4 resolution to prevent socket hang on Ubuntu 24.04
_orig_getaddrinfo = socket.getaddrinfo
def _getaddrinfo_ipv4(host, port, family=0, type=0, proto=0, flags=0):
    return _orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)
socket.getaddrinfo = _getaddrinfo_ipv4

from dotenv import load_dotenv
from agent.tools.sheets_tool import get_existing_places_from_sheet, update_enriched_row_in_sheet
from agent.tools.sheet_enricher_tool import (
    CSV_COLUMNS,
    NEGATIVE_PHRASES,
    FOREIGN_COUNTRIES,
    INDIA_LAT_MIN,
    INDIA_LAT_MAX,
    INDIA_LON_MIN,
    INDIA_LON_MAX,
    needs_repair,
    _rewrite,
    _resolve_coordinates,
    _is_valid_india_coord,
    fetch_verified_wikipedia,
    _google_search_consolidated,
    _load_state_places,
    _close_active_browser
)

load_dotenv()

FIELDS_TO_REPAIR = [
    ("Description", "description"),
    ("Recognition", "recognition"),
    ("culture", "culture"),
    ("History", "history"),
    ("Address_from_Capital", "address"),
    ("means_of_transport", "transport"),
    ("Famous_Dish", "food")
]


def _is_foreign_or_invalid_ref(ref_url: str, title: str, pname: str = "", city: str = "", state: str = "") -> bool:
    """Check if reference URL or title contains foreign markers, generic city/state articles, or obvious mismatches."""
    if not ref_url and not title:
        return False
    combined = f"{ref_url.lower()} {title.lower()}"
    for fc in FOREIGN_COUNTRIES:
        if fc in combined:
            return True

    from agent.tools.sheet_enricher_tool import _clean_tokens
    import difflib

    clean_p = _clean_tokens(pname)
    clean_t = _clean_tokens(title)
    if clean_t and clean_t.issubset({city.lower(), state.lower()}):
        if not clean_p.issubset({city.lower(), state.lower()}):
            return True

    if pname and title:
        overlap = len(clean_p & clean_t)
        sim = difflib.SequenceMatcher(None, pname.lower(), title.lower()).ratio()
        if overlap < len(clean_p) and (overlap / max(len(clean_p), 1) < 0.60 or sim < 0.75):
            return True

    return False


def _is_invalid_location_string(loc_str: str) -> bool:
    """Check if Location string is missing, invalid, or outside India bounds."""
    if not loc_str or not loc_str.strip():
        return True
    loc_lower = loc_str.strip().lower()
    if "not found" in loc_lower or "none" in loc_lower:
        return True

    # Parse lat, lon numbers
    nums = re.findall(r"[-+]?\d*\.\d+|\d+", loc_str)
    if len(nums) >= 2:
        try:
            lat = float(nums[0])
            lon = float(nums[1])
            return not (INDIA_LAT_MIN <= lat <= INDIA_LAT_MAX and INDIA_LON_MIN <= lon <= INDIA_LON_MAX)
        except ValueError:
            return True
    return True


def repair_state_places(state_name: str, city_name: str | None = None) -> str:
    """Scans and repairs missing, broken, or negative data in the state's Google Sheet.
    
    Args:
        state_name (str): State jiska data repair karna hai (e.g., 'Bihar', 'Uttarakhand').
        city_name (str | None): Optional city filter (e.g., 'Patna'). If None, scans entire state tab.
        
    Returns:
        str: Detailed summary of repaired places and updated rows.
    """
    from agent.task_controller import task_controller

    city_filter = city_name.strip().lower() if city_name else None
    display_target = f"{state_name}" + (f" ({city_name})" if city_name else "")
    print(f"\n🔍 [Sheet Repair] Starting deep audit for: {display_target}")

    existing_places = get_existing_places_from_sheet(state_name.title())
    if not existing_places:
        return f"No existing places found in the Google Sheet for '{state_name}'."

    # Load local JSON places for coordinate/metadata reference if available
    local_places_map = {}
    try:
        raw_local = _load_state_places(state_name)
        for lp in raw_local:
            lp_name = lp.get("name", "").strip().lower()
            if lp_name:
                local_places_map[lp_name] = lp
    except Exception as e:
        print(f"  ℹ Notice: Local JSON places could not be loaded ({e}). Will rely on API and web.")

    # Deduplicate rows by row_index
    unique_rows = {}
    for place_key, info in existing_places.items():
        r_idx = info["row_index"]
        if r_idx not in unique_rows:
            unique_rows[r_idx] = info["data"]

    sorted_row_indices = sorted(unique_rows.keys())
    total_rows = len(sorted_row_indices)
    task_controller.reset(f"Repairing {display_target}", total_rows)

    repaired_count = 0
    scanned_count = 0

    try:
        for idx_num, row_idx in enumerate(sorted_row_indices, start=1):
            row_data = unique_rows[row_idx]

            # Reconstruct row_dict
            row_dict = {}
            for i, col in enumerate(CSV_COLUMNS):
                row_dict[col] = row_data[i].strip() if i < len(row_data) else ""

            pname = row_dict.get("famous_place_name") or row_dict.get("Place") or ""
            city = (row_dict.get("district") or row_dict.get("Place") or "").strip().title()

            if not pname:
                continue

            # Apply city filter if provided
            if city_filter:
                row_city = city.lower()
                if not (city_filter in row_city or (row_city and row_city in city_filter)):
                    continue

            scanned_count += 1
            if not task_controller.check_point(idx_num, total_rows, pname, f"Repairing {display_target}"):
                print("  ⏹ Repair task stopped by user.")
                break

            print(f"\n  [{idx_num}/{total_rows}] Auditing: {pname} ({city}, {state_name})")

            row_needs_update = False
            reasons = []

            # ── 1. Audit Coordinates ─────────────────────────────────────
            curr_loc = row_dict.get("Location", "")
            if _is_invalid_location_string(curr_loc):
                print(f"    📍 Bad/Missing coordinates detected: '{curr_loc}' -> Re-resolving...")
                local_meta = local_places_map.get(pname.lower(), {})
                new_loc = _resolve_coordinates(
                    pname, city, state_name,
                    json_lat=local_meta.get("lat"),
                    json_lon=local_meta.get("lon")
                )
                if new_loc != curr_loc:
                    row_dict["Location"] = new_loc
                    row_needs_update = True
                    reasons.append("coordinates")
                    print(f"    ✅ Repaired Location: {new_loc}")

            # ── 2. Audit Wikipedia Reference, Title & Images ─────────────
            curr_ref = row_dict.get("reference", "")
            curr_title = row_dict.get("famous_place_title", "")
            curr_img = row_dict.get("Image URL from wikipedia", "")

            is_bad_ref = _is_foreign_or_invalid_ref(curr_ref, curr_title, pname=pname, city=city, state=state_name)
            is_missing_img = not curr_img.strip()

            wiki_data = None
            if is_bad_ref or is_missing_img:
                if is_bad_ref:
                    print(f"    ❌ Mismatched/Foreign reference detected: '{curr_ref}' (Title: '{curr_title}')")
                else:
                    print(f"    🖼️ Wikipedia images missing for: '{pname}'")

                wiki_data = fetch_verified_wikipedia(pname, city, state_name)
                if wiki_data.get("wiki_url"):
                    if curr_ref != wiki_data["wiki_url"]:
                        row_dict["reference"] = wiki_data["wiki_url"]
                        row_dict["famous_place_title"] = wiki_data["title"]
                        row_needs_update = True
                        reasons.append("wikipedia_reference")

                    if wiki_data.get("images"):
                        new_img_str = ", ".join(wiki_data["images"][:8])
                        if curr_img != new_img_str:
                            row_dict["Image URL from wikipedia"] = new_img_str
                            row_needs_update = True
                            reasons.append("wikipedia_images")
                            print(f"    ✅ Attached {len(wiki_data['images'])} verified Wikimedia images.")
                else:
                    # Not verified: clear any corrupted reference / wrong images
                    if is_bad_ref:
                        row_dict["reference"] = ""
                        row_dict["famous_place_title"] = pname
                        row_dict["Image URL from wikipedia"] = ""
                        row_needs_update = True
                        reasons.append("cleared_bad_wikipedia")
                        print(f"    🧹 Cleared corrupted foreign reference for: '{pname}'")

            # ── 3. Audit Text Fields ──────────────────────────────────────
            broken_fields = []
            for col_name, field_key in FIELDS_TO_REPAIR:
                val = row_dict.get(col_name, "")
                if needs_repair(val):
                    broken_fields.append((col_name, field_key, val))

            if broken_fields:
                print(f"    🛠 Broken/Negative text fields detected: {[bf[0] for bf in broken_fields]}")
                broken_keys = [bf[1] for bf in broken_fields]
                has_wiki = bool(wiki_data and wiki_data.get("extract") and len(wiki_data["extract"]) > 150)
                need_hist_cult = (not has_wiki) or any(k in broken_keys for k in ["history", "culture", "recognition", "description"])
                google_text, google_urls = _google_search_consolidated(pname, city, state_name, need_history_culture=need_hist_cult)

                combined_context = ""
                if wiki_data and wiki_data.get("extract"):
                    combined_context += wiki_data["extract"] + "\n\n"
                combined_context += google_text

                local_meta = local_places_map.get(pname.lower(), {})
                if not combined_context.strip() and local_meta.get("description"):
                    combined_context = local_meta["description"]

                # Append any new Google URLs
                existing_urls = [u.strip() for u in row_dict.get("Google Search Links", "").splitlines() if u.strip()]
                for gu in google_urls:
                    if gu not in existing_urls:
                        existing_urls.append(gu)
                if existing_urls:
                    row_dict["Google Search Links"] = "\n".join(existing_urls)

                for col_name, field_key, old_val in broken_fields:
                    print(f"      ✍ Repairing [{col_name}]...")
                    repaired_text = _rewrite(field_key, combined_context, pname, city, state_name)
                    if repaired_text and not needs_repair(repaired_text):
                        row_dict[col_name] = repaired_text
                        row_needs_update = True
                        reasons.append(col_name)
                    else:
                        print(f"      ⚠ Could not generate valid content for {col_name}")

            # ── 4. Apply In-Place Sheet Update ───────────────────────────
            if row_needs_update:
                flat_row = [row_dict.get(col, "") for col in CSV_COLUMNS]
                flat_row[0] = row_data[0] if row_data else str(row_idx - 1)

                print(f"    ⬆ Updating Google Sheet row {row_idx} ({', '.join(reasons)})...")
                res_msg = update_enriched_row_in_sheet(state_name.title(), row_idx, flat_row)
                print(f"    ✅ {res_msg}")
                repaired_count += 1
                time.sleep(1.5)  # Avoid Google Sheets API quota limits
            else:
                print(f"    ✨ Row {row_idx} is already pristine. No repairs needed.")

    except Exception as e:
        print(f"\n❌ Unexpected error during repair process: {e}")
    finally:
        print("🛑 Resetting browser session...")
        _close_active_browser()

    return f"Sheet repair completed for {display_target}. Audited {scanned_count} rows, successfully repaired {repaired_count} rows."


if __name__ == "__main__":
    pass
