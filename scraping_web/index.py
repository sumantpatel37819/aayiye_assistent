"""
scraping_web/index.py — Links lo aur har link ko browser se scrape karo.
"""

import asyncio
import sys
from pathlib import Path

import scraping_web.crawl4ai_scraper as crawl4ai_scraper
import scraping_web.htmlextract as htmlextract

BASE_DIR    = Path(__file__).parent
PROJECT_DIR = BASE_DIR.parent

if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

import asyncio

async def run_query(query: str, num_results: int = 2):
    """
    Query ke liye:
      1. Background me Selenium (undetected_chromedriver) use karke Google search karo.
      2. Top links visit karke unka text nikalo.
      3. Return raw results jisko baad me LLM refine karega.
    """
    print(f"\n{'='*50}")
    print(f"  Query: {query}")
    print(f"{'='*50}")

    from gettinglinks.google_login_search import search_and_extract_gemini_and_links
    
    raw_text = await asyncio.to_thread(search_and_extract_gemini_and_links, query, num_results)
    
    if not raw_text:
        print("❌ Koi data scrape nahi ho paaya.")
        return []

    print(f"\n✅ Data extract ho gaya (Ab LLM isko refine karega).")
    return [(raw_text, [])]


if __name__ == "__main__":
    query = input("Search query enter karo: ").strip()
    asyncio.run(run_query(query))