"""
scraping_web/wiki_crawl4ai.py

Wikipedia page ko crawl4ai (Playwright browser) se directly scrape karo.

Yeh module tab use hota hai jab Wikipedia REST API title mismatch ki wajah
se khaali/galat data return kare.

Functions:
    scrape_wikipedia_page(wiki_url)  → async
    scrape_wikipedia_sync(wiki_url)  → sync wrapper (sheet_enricher ke liye)
"""

import asyncio
import re
import urllib.parse

from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig


# ─────────────────────────────────────────────
# Browser Config — headless, Wikipedia-friendly
# ─────────────────────────────────────────────

_BROWSER_CFG = BrowserConfig(
    headless=True,
    verbose=False,
    user_agent=(
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    java_script_enabled=True,
    accept_downloads=False,
)

_RUN_CFG = CrawlerRunConfig(
    cache_mode=CacheMode.BYPASS,
    wait_until="domcontentloaded",   # Wikipedia static hai, networkidle zaroori nahi
    page_timeout=30000,
    delay_before_return_html=1.5,
    remove_overlay_elements=True,
    process_iframes=False,
    exclude_external_links=True,
    magic=True,
)

# Wikimedia CDN image pattern — sirf real article images
_WIKIMEDIA_IMG_RE = re.compile(
    r'https://upload\.wikimedia\.org/wikipedia/(?:commons|en)/[^\s\)\"\']+\.(?:jpg|jpeg|png)',
    re.IGNORECASE,
)

# Wikipedia geo meta tag: "25.1347;85.4439"
_GEO_META_RE = re.compile(r'(\d{1,3}\.\d+);(\d{1,3}\.\d+)')

# Small/icon images ko filter karna — filename hints (NOTE: 'commons' NOT here — all Wikimedia URLs have it)
_SKIP_IMG_KEYWORDS = (
    "icon", "logo", "flag", "button", "arrow", "edit",
    "portal", "star", "lock", "symbol",
    "OOjs_UI", "Wikidata", "Wikipedia-logo", "wikimedia-logo",
    "thumb/1", "thumb/2", "thumb/3",
)


def _filter_wikimedia_images(raw_markdown: str, html: str) -> list:
    """
    crawl4ai ke markdown + raw HTML dono se Wikimedia image URLs extract karo.
    Sirf proper article photos lo — icons/flags/logos skip karo.
    """
    urls_found = set()

    # Markdown se URLs
    for url in _WIKIMEDIA_IMG_RE.findall(raw_markdown or ""):
        urls_found.add(url.rstrip(")\"'"))

    # HTML se bhi dhundho (markdown se chhoot jaate hain)
    for url in _WIKIMEDIA_IMG_RE.findall(html or ""):
        urls_found.add(url.rstrip(")\"'"))

    # Filter: skip small icons / logos
    clean = []
    for url in urls_found:
        url_lower = url.lower()
        if any(kw in url_lower for kw in _SKIP_IMG_KEYWORDS):
            continue
        # Thumb URLs ko full-size mein convert karo
        # Example: /thumb/a/ab/File.jpg/320px-File.jpg → /a/ab/File.jpg
        if "/thumb/" in url:
            # Remove the /thumb/ part and the trailing dimension
            try:
                parts = url.split("/thumb/")
                base   = parts[0]
                rest   = parts[1]                       # "a/ab/File.jpg/320px-File.jpg"
                # Remove last path segment (the resized filename)
                rest_parts = rest.rsplit("/", 1)
                if len(rest_parts) == 2:
                    full_url = base + "/" + rest_parts[0]
                    url = full_url
            except Exception:
                pass  # agar split fail ho toh original URL use karo
        if url not in clean:
            clean.append(url)

    return clean[:10]  # Max 10 images


def _extract_coordinates_from_html(html: str) -> tuple:
    """
    Wikipedia page ke HTML se lat/lon extract karo.
    Tries:
      1. <meta name="geo.position" content="25.1347;85.4439">
      2. <span class="geo">25.1347; 85.4439</span>
      3. "coordinates" keyword ke baad numbers dhundho
    """
    if not html:
        return None, None

    # Method 1: geo.position meta tag
    m = re.search(r'geo\.position"[^>]*content="([0-9.\-]+);([0-9.\-]+)"', html, re.IGNORECASE)
    if m:
        try:
            return float(m.group(1)), float(m.group(2))
        except ValueError:
            pass

    # Method 2: <span class="geo">
    m = re.search(r'class="geo"[^>]*>([0-9.\-]+);\s*([0-9.\-]+)', html, re.IGNORECASE)
    if m:
        try:
            return float(m.group(1)), float(m.group(2))
        except ValueError:
            pass

    # Method 3: data-lat / data-lon attributes
    m_lat = re.search(r'data-lat="([0-9.\-]+)"', html)
    m_lon = re.search(r'data-lon="([0-9.\-]+)"', html)
    if m_lat and m_lon:
        try:
            return float(m_lat.group(1)), float(m_lon.group(1))
        except ValueError:
            pass

    return None, None


def _clean_text_from_markdown(raw_markdown: str) -> str:
    """Markdown se images remove karo, baaki text clean karo."""
    if not raw_markdown:
        return ""
    # Image syntax remove
    text = re.sub(r'!\[.*?\]\(.*?\)', '', raw_markdown)
    # Markdown links → sirf link text rakhho
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    # Multiple blank lines → single
    text = re.sub(r'\n{3,}', '\n\n', text)
    # Clean lines
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines)


# ─────────────────────────────────────────────
# Main async scraper
# ─────────────────────────────────────────────

async def scrape_wikipedia_page(wiki_url: str) -> dict:
    """
    crawl4ai se Wikipedia page scrape karo.

    Args:
        wiki_url: Full Wikipedia URL (e.g. https://en.wikipedia.org/wiki/Nalanda)

    Returns:
        dict: {
            "extract":  str  — article text (clean),
            "images":   list — Wikimedia CDN image URLs,
            "lat":      float | None,
            "lon":      float | None,
            "success":  bool
        }
    """
    result = {"extract": "", "images": [], "lat": None, "lon": None, "success": False}

    print(f"    🕷 [crawl4ai] Scraping Wikipedia: {wiki_url}")

    try:
        async with AsyncWebCrawler(config=_BROWSER_CFG) as crawler:
            res = await crawler.arun(url=wiki_url, config=_RUN_CFG)

            if not res.success:
                print(f"    ❌ [crawl4ai] Scrape failed: {wiki_url}")
                return result

            raw_markdown = res.markdown or ""
            raw_html     = res.html     or ""

            # ── Text ────────────────────────────────────────
            extract = _clean_text_from_markdown(raw_markdown)
            if len(extract) > 200:
                result["extract"] = extract
                print(f"    ✅ [crawl4ai] Text mila: {len(extract)} chars")
            else:
                print(f"    ⚠ [crawl4ai] Text bahut chota: {len(extract)} chars")

            # ── Images ──────────────────────────────────────
            images = _filter_wikimedia_images(raw_markdown, raw_html)
            result["images"] = images
            print(f"    🖼 [crawl4ai] Images mili: {len(images)}")

            # ── Coordinates ─────────────────────────────────
            lat, lon = _extract_coordinates_from_html(raw_html)
            if lat and lon:
                result["lat"] = lat
                result["lon"] = lon
                print(f"    📍 [crawl4ai] Coordinates: {lat}, {lon}")
            else:
                print(f"    ⚠ [crawl4ai] Coordinates nahi mili page se")

            result["success"] = bool(result["extract"] or result["images"])

    except Exception as e:
        print(f"    ❌ [crawl4ai] Exception: {e}")

    return result


# ─────────────────────────────────────────────
# Sync wrapper — sheet_enricher_tool.py ke liye
# ─────────────────────────────────────────────

def scrape_wikipedia_sync(wiki_url: str) -> dict:
    """
    scrape_wikipedia_page() ka synchronous wrapper.

    Existing event loop detect karta hai (nest_asyncio fallback ke saath),
    isliye yeh function sync code (sheet_enricher_tool.py) mein safely call ho sakta hai.

    Args:
        wiki_url: Full Wikipedia URL

    Returns:
        dict: same as scrape_wikipedia_page()
    """
    try:
        # Check: kya already koi event loop chal raha hai?
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # nest_asyncio allow karta hai nested run_until_complete
            try:
                import nest_asyncio
                nest_asyncio.apply()
            except ImportError:
                print("    ⚠ nest_asyncio install nahi hai — async fallback skip")
                return {"extract": "", "images": [], "lat": None, "lon": None, "success": False}
            return loop.run_until_complete(scrape_wikipedia_page(wiki_url))
        else:
            return asyncio.run(scrape_wikipedia_page(wiki_url))
    except RuntimeError:
        # Naya loop banao as last resort
        try:
            return asyncio.run(scrape_wikipedia_page(wiki_url))
        except Exception as e:
            print(f"    ❌ [crawl4ai sync] RuntimeError: {e}")
            return {"extract": "", "images": [], "lat": None, "lon": None, "success": False}


# ─────────────────────────────────────────────
# Quick test (standalone)
# ─────────────────────────────────────────────

if __name__ == "__main__":
    test_url = "https://en.wikipedia.org/wiki/Nalanda"
    print(f"\n🧪 Testing: {test_url}\n")
    data = scrape_wikipedia_sync(test_url)
    print(f"\n📄 Extract (first 500 chars):\n{data['extract'][:500]}")
    print(f"\n🖼 Images ({len(data['images'])}):")
    for img in data['images'][:5]:
        print(f"  {img}")
    print(f"\n📍 Coordinates: {data['lat']}, {data['lon']}")
    print(f"\n✅ Success: {data['success']}")
