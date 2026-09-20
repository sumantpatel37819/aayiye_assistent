"""
agent/tools/pinecone_sync_tool.py

Pipeline to chunk tourist destination CSV rows, embed them using Ollama's
'mxbai-embed-large' (1024 dimensions), and batch-upsert into Pinecone serverless index.
"""

import os
import csv
import time
import requests
from pathlib import Path
from dotenv import load_dotenv
from pinecone import Pinecone, ServerlessSpec

from agent.task_controller import task_controller

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CSV_DIR = PROJECT_ROOT / "sheet_works" / "db" / "details_places"

PINECONE_API_KEY = (os.getenv("PINECONE_API_KEY") or "").strip()
PINECONE_INDEX_NAME = (os.getenv("PINECONE_INDEX_NAME") or "sonukumar").strip().lower()
OLLAMA_EMBED_URL = "http://127.0.0.1:11434/api/embeddings"
EMBED_MODEL = "mxbai-embed-large:latest"
VECTOR_DIM = 1024


def get_pinecone_index():
    """Ensure Pinecone index exists and return the index client."""
    if not PINECONE_API_KEY:
        raise ValueError("PINECONE_API_KEY is not set in .env file.")

    pc = Pinecone(api_key=PINECONE_API_KEY)
    existing_indexes = [idx.name for idx in pc.list_indexes()]

    if PINECONE_INDEX_NAME not in existing_indexes:
        print(f"🌲 Creating new Pinecone index: '{PINECONE_INDEX_NAME}' (dim={VECTOR_DIM}, metric=cosine)...")
        pc.create_index(
            name=PINECONE_INDEX_NAME,
            dimension=VECTOR_DIM,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1")
        )
        time.sleep(3)

    return pc.Index(PINECONE_INDEX_NAME)


def get_embedding(text: str, is_query: bool = False) -> list[float]:
    """Generate 1024-dim embedding via Ollama mxbai-embed-large."""
    prompt_text = text.strip()
    if is_query:
        prompt_text = f"Represent this sentence for searching relevant passages: {prompt_text}"

    resp = requests.post(
        OLLAMA_EMBED_URL,
        json={"model": EMBED_MODEL, "prompt": prompt_text},
        timeout=30
    )
    resp.raise_for_status()
    data = resp.json()
    embedding = data.get("embedding", [])
    if not embedding or len(embedding) != VECTOR_DIM:
        raise ValueError(f"Expected {VECTOR_DIM} dimensions from {EMBED_MODEL}, got {len(embedding)}")
    return embedding


def make_semantic_chunk(row: dict) -> tuple[str, dict]:
    """
    Takes 1 CSV row and returns:
      (plain_text_for_embedding, metadata_for_pinecone)
    """
    p_id = int(row.get("place_id") or 0)
    name = (row.get("name") or "").strip()
    state = (row.get("state") or "").strip()
    city = (row.get("city") or "").strip()
    category = (row.get("category") or "tourist attraction").strip()
    other_names = (row.get("other_names") or "").strip()
    coord_str = (row.get("coordinate") or "").strip()
    opening_hour = (row.get("opening_hour") or "Open daily").strip()
    avg_time_spend = (row.get("avg_time_spend") or "1 to 2 hours").strip()
    entry_fee = (row.get("entry_fee") or "Free entry").strip()
    best_time = (row.get("best_time_to_visit") or "").strip()
    description = (row.get("description") or "").strip()

    title = f"{name} ({other_names})" if other_names else name

    plain_text = (
        f"Destination: {title} ({category})\n"
        f"Location: {city}, {state} | Coordinates: {coord_str}\n"
        f"Operating Timings: {opening_hour}\n"
        f"Entry Fee & Tickets: {entry_fee}\n"
        f"Recommended Duration: {avg_time_spend}\n"
        f"Best Time to Visit & Traveler Suitability: {best_time}\n"
        f"About the Place: {description}"
    ).strip()

    lat, lng = None, None
    if "," in coord_str:
        try:
            parts = coord_str.split(",")
            lat = float(parts[0].strip())
            lng = float(parts[1].strip())
        except ValueError:
            pass

    metadata = {
        "place_id": p_id,
        "name": name,
        "state": state,
        "city": city,
        "category": category,
        "other_names": other_names,
        "lat": lat if lat is not None else 0.0,
        "lng": lng if lng is not None else 0.0,
        "opening_hour": opening_hour,
        "avg_time_spend": avg_time_spend,
        "entry_fee": entry_fee,
        "best_time_to_visit": best_time,
        "text": plain_text
    }

    return plain_text, metadata


def push_state_csv_to_pinecone(state_name: str, batch_size: int = 50) -> str:
    """
    Read details_places/<state>_places.csv, embed all places, and push to Pinecone.
    """
    state_slug = state_name.lower().strip().replace(" ", "_").replace("-", "_")
    csv_file = CSV_DIR / f"{state_slug}_places.csv"

    if not csv_file.exists():
        err = f"❌ CSV file not found for state '{state_name}': {csv_file}\nPlease create CSV first."
        print(err)
        return err

    print(f"\n🚀 [Pinecone Sync] Starting vector ingestion for state: '{state_name.title()}'")
    print(f"   Source CSV: {csv_file}")
    print(f"   Target Index: '{PINECONE_INDEX_NAME}' (Embedding: {EMBED_MODEL})")

    with open(csv_file, mode="r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        return f"⚠ No rows found in {csv_file.name}."

    index = get_pinecone_index()
    total_places = len(rows)
    task_controller.reset(f"Syncing {state_name} to Pinecone", total_places)

    records_to_upsert = []
    pushed_count = 0

    try:
        for idx, row in enumerate(rows, start=1):
            pname = row.get("name", f"Place {idx}")
            p_id = row.get("place_id", str(idx))

            if not task_controller.check_point(idx, total_places, pname, f"Embedding & Syncing to Pinecone"):
                print("  ⏹ Pinecone sync stopped by user.")
                break

            plain_text, metadata = make_semantic_chunk(row)
            vector = get_embedding(plain_text, is_query=False)

            vector_id = f"{state_slug}_{p_id}"
            records_to_upsert.append({
                "id": vector_id,
                "values": vector,
                "metadata": metadata
            })

            if len(records_to_upsert) >= batch_size or idx == total_places:
                print(f"  🌲 Upserting batch of {len(records_to_upsert)} vectors to Pinecone [{idx}/{total_places}]...")
                index.upsert(vectors=records_to_upsert)
                pushed_count += len(records_to_upsert)
                records_to_upsert = []

        summary_msg = (
            f"🎉 Pinecone Vector Sync Completed!\n"
            f"• State: {state_name.title()}\n"
            f"• Total Places Embedded & Pushed: {pushed_count} / {total_places}\n"
            f"• Pinecone Index: '{PINECONE_INDEX_NAME}' ({VECTOR_DIM} dims)\n"
            f"• Embedding Model: {EMBED_MODEL}"
        )
        print(f"\n{summary_msg}")
        return summary_msg

    except Exception as e:
        err_msg = f"❌ Error during Pinecone sync: {e}"
        print(err_msg)
        return err_msg


if __name__ == "__main__":
    import sys
    state = sys.argv[1] if len(sys.argv) > 1 else "Bihar"
    push_state_csv_to_pinecone(state)
