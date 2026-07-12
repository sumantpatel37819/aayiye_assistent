"""
agent/tools/json_sync_tool.py — Sync & update tourist place JSON files between source Plces_db and local Plces_db.

Rules implemented:
1. Source directory: E:/ProjectWebsite/tourKaro/tourKaro_reDesign/Plces_db
2. Destination directory: sheet_works/db/Plces_db
3. places-name.json in source corresponds to places-name-bihar.json in destination.
4. For all state and Nepal/Bhutan files (places-name*.json), check destination against source.
5. If destination file does not exist, create it in destination in destination's clean format.
6. If destination file exists, update it according to source (fill missing descriptions, add missing places/cities) while keeping destination's format.
"""

import json
import sys
from pathlib import Path
from langchain_core.tools import tool

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ─────────────────────────────────────────────
# Directories
# ─────────────────────────────────────────────
SOURCE_DB_DIR = Path(r"E:\ProjectWebsite\tourKaro\tourKaro_reDesign\Plces_db")
DEST_DB_DIR = Path(__file__).parent.parent.parent / "sheet_works" / "db" / "Plces_db"


def dump_single_line(obj: dict) -> str:
    """Dump a dictionary into a single line JSON string with spaces inside braces."""
    s = json.dumps(obj, ensure_ascii=False)
    if s.startswith('{') and s.endswith('}'):
        return '{ ' + s[1:-1].strip() + ' }'
    return s


def format_places_json(data: dict) -> str:
    """
    Format JSON with 2-space indentation, keeping place dictionaries inside 'places' arrays on a single line.
    This preserves the destination clean format ('iske formate me').
    """
    place_map = {}
    counter = [0]
    
    def _prepare(obj):
        if isinstance(obj, dict):
            new_dict = {}
            for k, v in obj.items():
                if k == "places" and isinstance(v, list):
                    new_list = []
                    for item in v:
                        if isinstance(item, dict):
                            token = f"__PLACE_TOKEN_{counter[0]}__"
                            place_map[f'"{token}"'] = dump_single_line(item)
                            new_list.append(token)
                            counter[0] += 1
                        else:
                            new_list.append(item)
                    new_dict[k] = new_list
                else:
                    new_dict[k] = _prepare(v)
            return new_dict
        elif isinstance(obj, list):
            return [_prepare(item) for item in obj]
        else:
            return obj

    modified_data = _prepare(data)
    raw_json = json.dumps(modified_data, indent=2, ensure_ascii=False)
    
    for token_str, replacement in place_map.items():
        raw_json = raw_json.replace(token_str, replacement)
        
    return raw_json + "\n"


def _remove_descriptions(obj, stats):
    """Remove any description field to maintain destination format (no description)."""
    pass # Modified: Keep descriptions if they exist

def _count_items(obj, stats):
    """Count places in a data structure."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "places" and isinstance(v, list):
                stats["places_added"] += len(v)
            else:
                _count_items(v, stats)
    elif isinstance(obj, list):
        for item in obj:
            _count_items(item, stats)


def _merge_dicts(dst: dict, src: dict, stats: dict):
    """
    Recursively merge source dictionary into destination dictionary.
    - Fills missing cities/states/regions.
    - Appends missing places and updates missing/different place attributes.
    """
    for k, src_val in src.items():
        if k not in dst:
            dst[k] = src_val
            _remove_descriptions(dst[k], stats)
            _count_items(dst[k], stats)
        else:
            if isinstance(dst[k], dict) and isinstance(src_val, dict):
                _merge_dicts(dst[k], src_val, stats)
            elif k == "places" and isinstance(dst[k], list) and isinstance(src_val, list):
                existing_names = {}
                for idx, p in enumerate(dst[k]):
                    if isinstance(p, dict) and "name" in p:
                        existing_names[p["name"].strip().lower()] = p
                
                for src_place in src_val:
                    if not isinstance(src_place, dict) or "name" not in src_place:
                        continue
                    pname = src_place["name"].strip().lower()
                    if pname not in existing_names:
                        dst[k].append(src_place)
                        existing_names[pname] = src_place
                        stats["places_added"] += 1
                    else:
                        # Update fields from source if missing or different
                        dst_place = existing_names[pname]
                        place_changed = False
                        for field, fval in src_place.items():
                            if field == "description":
                                continue
                            if field not in dst_place or dst_place[field] != fval:
                                dst_place[field] = fval
                                place_changed = True
                        if place_changed:
                            stats["places_updated"] += 1


def run_json_sync() -> str:
    """Execute the sync process from source Plces_db to destination Plces_db."""
    if not SOURCE_DB_DIR.exists():
        return f"❌ Source directory not found: {SOURCE_DB_DIR}"
    
    DEST_DB_DIR.mkdir(parents=True, exist_ok=True)
    
    source_files = list(SOURCE_DB_DIR.glob("places-name*.json"))
    if not source_files:
        return f"❌ No places-name*.json files found in {SOURCE_DB_DIR}"
        
    created_files = []
    updated_files = []
    total_stats = {
        "descriptions_removed": 0,
        "places_added": 0,
        "places_updated": 0
    }
    
    print(f"\n🚀 Starting JSON Sync from {SOURCE_DB_DIR} to {DEST_DB_DIR}...\n")
    
    for src_file in sorted(source_files):
        # Rule: places-name.json jo waha hai wo yaha ke bihar wala ka hai
        if src_file.name == "places-name.json":
            dst_filename = "places-name-bihar.json"
        else:
            dst_filename = src_file.name
            
        dst_file = DEST_DB_DIR / dst_filename
        
        try:
            src_data = json.loads(src_file.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  ⚠️ Error reading source {src_file.name}: {e}")
            continue
            
        file_stats = {
            "descriptions_removed": 0,
            "places_added": 0,
            "places_updated": 0
        }
        
        if not dst_file.exists():
            # Rule: jo json yaha exit nahi karta hoga usko yaha create karna
            dst_data = {}
            _merge_dicts(dst_data, src_data, file_stats)
            _remove_descriptions(dst_data, file_stats)
            formatted_json = format_places_json(dst_data)
            dst_file.write_text(formatted_json, encoding="utf-8")
            created_files.append(dst_filename)
            print(f"  ✨ Created: {dst_filename} (Places: {file_stats['places_added']})")
        else:
            # Rule: jo exit kare usko yaha update karna
            try:
                dst_data = json.loads(dst_file.read_text(encoding="utf-8"))
            except Exception as e:
                print(f"  ⚠️ Error reading destination {dst_filename}, recreating: {e}")
                dst_data = {}
                
            _merge_dicts(dst_data, src_data, file_stats)
            _remove_descriptions(dst_data, file_stats)
            formatted_json = format_places_json(dst_data)
            dst_file.write_text(formatted_json, encoding="utf-8")
            
            if sum(file_stats.values()) > 0:
                updated_files.append(dst_filename)
                print(f"  🔄 Updated: {dst_filename} (New Places: {file_stats['places_added']}, Updated Places: {file_stats['places_updated']}, Descriptions Removed: {file_stats['descriptions_removed']})")
            else:
                print(f"  ✔️ Checked: {dst_filename} (Already up-to-date)")
                
        for k in total_stats:
            total_stats[k] += file_stats[k]
            
    summary_lines = [
        "✅ **JSON Files Sync & Update Completed!**",
        f"- **Total files checked:** {len(source_files)}",
        f"- **New files created:** {len(created_files)}",
        f"- **Existing files updated:** {len(updated_files)}",
        f"- **Total descriptions removed:** {total_stats['descriptions_removed']}",
        f"- **Total new places added:** {total_stats['places_added']}",
        f"- **Total existing places updated:** {total_stats['places_updated']}"
    ]
    if created_files:
        summary_lines.append(f"\n**Created Files:** {', '.join(created_files)}")
    if updated_files:
        summary_lines.append(f"\n**Updated Files:** {', '.join(updated_files)}")
        
    return "\n".join(summary_lines)


@tool
def sync_places_json() -> str:
    """Use this tool when instructed to update or sync JSON tourist place files from external database (tourKaro Plces_db) into local Places_db."""
    return run_json_sync()
