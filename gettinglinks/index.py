"""
gettinglinks/index.py — Query ke liye links fetch karo.

Priority order:
  1. Browser Search (Playwright + Google) — sabse reliable
  2. SerpAPI                             — fallback (API key chahiye)
  3. DuckDuckGo                          — fallback (no key needed)
"""

import asyncio

from gettinglinks.browser_search import google_search_links
from gettinglinks.duckduckgo import get_duckduckgo_links
from gettinglinks.serp_link import get_serp_links


def normalize_link(link):
    clean_link = link.rstrip("/")
    clean_link = clean_link.replace("https://www.", "https://")
    clean_link = clean_link.replace("http://www.", "http://")
    return clean_link


def remove_duplicate_links(links):
    unique_links = []
    seen_links = []

    for link in links:
        normal_link = normalize_link(link)
        if normal_link not in seen_links:
            unique_links.append(link)
            seen_links.append(normal_link)

    return unique_links


def print_links(title, links):
    print(f"\n{title}")
    if not links:
        print("  Koi link nahi mila.")
        return
    for number, link in enumerate(links, start=1):
        print(f"  {number}. {link}")


async def get_links_async(query: str, num_results: int = 4):
    """
    Async version — Playwright browser se Google search karo.
    Returns: (browser_links, fallback_links, all_links)
    """
    browser_links = []
    fallback_links = []

    # ── Primary: Real browser Google search ──────────────
    try:
        browser_links = await google_search_links(query, num_results=num_results)
    except Exception as e:
        print(f"⚠ Browser search fail hui: {e}")
        print("  SerpAPI + DuckDuckGo fallback pe ja raha hoon...")

    # ── Fallback: SerpAPI + DuckDuckGo ───────────────────
    if not browser_links:
        serp  = get_serp_links(query)
        ddg   = get_duckduckgo_links(query)
        fallback_links = remove_duplicate_links(serp + ddg)

    all_links = remove_duplicate_links(browser_links + fallback_links)

    return browser_links, fallback_links, all_links


def get_links(query: str, num_results: int = 4):
    """
    Sync wrapper — asyncio loop se call karo.
    Returns: (browser_links, fallback_links, all_links)
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Already inside an async context — coroutine return karo
            # (caller asyncio.ensure_future ya await use kare)
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, get_links_async(query, num_results))
                return future.result()
        else:
            return loop.run_until_complete(get_links_async(query, num_results))
    except RuntimeError:
        return asyncio.run(get_links_async(query, num_results))


def main():
    query = input("Search query enter karo: ").strip()
    if not query:
        print("Query empty nahi honi chahiye.")
        return

    browser_links, fallback_links, all_links = asyncio.run(get_links_async(query))

    print_links("Browser (Google) links:", browser_links)
    print_links("Fallback links:", fallback_links)
    print_links("Combined links:", all_links)


if __name__ == "__main__":
    main()
