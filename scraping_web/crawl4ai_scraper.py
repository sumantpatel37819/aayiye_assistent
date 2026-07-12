"""
crawl4ai_scraper.py — Real browser (Playwright) se web pages scrape karo.

crawl4ai ke andar Playwright hai isliye JavaScript-heavy sites bhi scrape hoti hain.
Better config:
  - Network idle tak wait karo (not just 'commit')
  - User agent set karo
  - Overlays + popups hatao
  - JS execute hone do
"""

import asyncio
import re
import time
from pathlib import Path
from urllib.parse import urlparse

from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig


RAW_HTML_DIR = Path(__file__).parent / "raw_html"
DELETE_AFTER_SECONDS = 48 * 60 * 60  # 48 ghante ke baad purani files hatao

# ─────────────────────────────────────────────
# Browser Config — ek baar banao, reuse karo
# ─────────────────────────────────────────────
BROWSER_CFG = BrowserConfig(
    headless=True,       # Background mein chal (Google search alag browser mein khulta hai)
    verbose=False,
    user_agent=(
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    java_script_enabled=True,
    accept_downloads=False,
)


def delete_old_html_files():
    RAW_HTML_DIR.mkdir(exist_ok=True)
    current_time = time.time()
    for html_file in RAW_HTML_DIR.glob("*.html"):
        file_age = current_time - html_file.stat().st_mtime
        if file_age > DELETE_AFTER_SECONDS:
            html_file.unlink()


def make_html_file_name(url):
    parsed_url = urlparse(url)
    website_name = parsed_url.netloc or "website"
    website_name = re.sub(r"[^a-zA-Z0-9_-]", "_", website_name)
    current_time = time.strftime("%Y%m%d_%H%M%S")
    return f"{website_name}_{current_time}.html"


def save_raw_html(url, html):
    if not html:
        return None
    RAW_HTML_DIR.mkdir(exist_ok=True)
    file_name = make_html_file_name(url)
    file_path = RAW_HTML_DIR / file_name
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  💾 HTML saved: {file_path.name}")
    return file_path


# ─────────────────────────────────────────────
# Main scraper
# ─────────────────────────────────────────────

async def scrape_url(url: str, crawler: AsyncWebCrawler = None):
    """
    URL ko real browser se scrape karo.
    """
    delete_old_html_files()
    print(f"  🕷 Scraping: {url}")

    run_config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        wait_until="networkidle",      # Network idle hone tak wait
        page_timeout=30000,            # 30 sec timeout
        delay_before_return_html=2.0,  # 2 sec extra wait after load
        scroll_delay=0.8,
        remove_overlay_elements=True,
        process_iframes=False,
        exclude_external_links=True,
        magic=True,                    # Auto-handle popups
    )

    try:
        if crawler:
            result = await crawler.arun(url=url, config=run_config)
            return await _process_result(url, result)
        else:
            async with AsyncWebCrawler(config=BROWSER_CFG) as new_crawler:
                result = await new_crawler.arun(url=url, config=run_config)
                return await _process_result(url, result)

    except Exception as e:
        print(f"  ❌ Scraping error ({url}): {e}")
        return None, []


async def _process_result(url, result):
    if not result.success:
        print(f"  ❌ Scrape fail: {url}")
        return None, []

    html_file_path = save_raw_html(url, result.html)
    raw_markdown   = result.markdown or ""

    # Images nikalo
    all_images = re.findall(r"!\[.*?\]\((.*?)\)", raw_markdown)
    clean_images = [
        img for img in all_images
        if any(kw in img for kw in [
            "banner", "thumbnail", "photo-gallery",
            "photo-gallery__desktop", "images-desti",
            "maps.googleapis"
        ])
    ]

    # Text clean karo
    clean_text = re.sub(r"!\[.*?\]\(.*?\)", "", raw_markdown)
    clean_text = "\n".join(
        line.strip()
        for line in clean_text.splitlines()
        if line.strip()
    )

    if clean_text:
        preview = clean_text[:200].replace("\n", " ")
        print(f"  ✅ Text mila ({len(clean_text)} chars): {preview}...")
    else:
        print(f"  ⚠ Text extract nahi hua: {url}")

    return html_file_path, clean_images


# ─────────────────────────────────────────────
# Standalone runner
# ─────────────────────────────────────────────

async def _interactive():
    while True:
        url = input("URL enter karo (ya 'exit'): ").strip()
        if url.lower() == "exit":
            break
        html_path, images = await scrape_url(url)
        print(f"HTML: {html_path}")
        print(f"Images: {images}")


def run():
    asyncio.run(_interactive())


if __name__ == "__main__":
    run()
