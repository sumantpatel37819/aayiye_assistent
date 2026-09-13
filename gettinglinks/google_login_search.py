"""
google_login_search.py

Playwright se Chrome browser automate karo, Google pe search karo,
AI Overview extract karo (multi-source summary) aur web links ka text lo.

Strategy:
  PRIMARY  → Chrome (Playwright + stealth) → Google AI Overview
  FALLBACK1 → Top web links content (Chrome se hi)
  FALLBACK2 → SerpAPI → AI Overview ya links → requests se text
  FALLBACK3 → DuckDuckGo → links → requests se text
"""

import os
import re
import time
import random
import threading
import requests
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()
GMAIL_ID       = os.getenv("GMAIL_ID", "")
GMAIL_PASSWORD = os.getenv("GMAIL_PASSWORD", "")
SERP_API_KEY   = os.getenv("SERP_API_KEY", "")

# ─────────────────────────────────────────────────────────────────────────────
# Profile setup
# Dedicated playwright_profile folder -- blank session kafi hai Google search ke liye
# Real Chrome cookies copy NAHI karte -- fingerprint mismatch se CAPTCHA aata hai
# ─────────────────────────────────────────────────────────────────────────────

import os as _os

_PW_PROFILE_DIR = str(Path(__file__).resolve().parent.parent / "playwright_profile")
_os.makedirs(_PW_PROFILE_DIR, exist_ok=True)

# Global playwright/browser objects (singleton)
_pw        = None
_browser   = None
_context   = None
_page      = None


# ─────────────────────────────────────────────────────────────────────────────
# Browser lifecycle
# ─────────────────────────────────────────────────────────────────────────────

def _get_page():
    """
    Ek visible Chrome window kholo (Playwright + stealth).
    Persistent profile se login session save rehti hai.
    """
    global _pw, _browser, _context, _page

    # Already alive check
    if _page is not None:
        try:
            _ = _page.title()  # raises if closed
            return _page
        except Exception:
            _page = _context = _browser = _pw = None

    print("[Browser] Playwright Chromium start ho raha hai...")
    try:
        from playwright.sync_api import sync_playwright

        # playwright-stealth: try v2 (Stealth class) then v1 (stealth_sync)
        try:
            from playwright_stealth import Stealth
            _stealth_obj = Stealth()
            _apply_stealth = lambda pg: _stealth_obj.apply_stealth_sync(pg)
        except ImportError:
            try:
                from playwright_stealth import stealth_sync
                _apply_stealth = stealth_sync
            except ImportError:
                _apply_stealth = lambda pg: None

        _pw = sync_playwright().start()
        _browser = _pw.chromium.launch_persistent_context(
            user_data_dir=_PW_PROFILE_DIR,
            headless=False,
            args=[
                "--start-maximized",
                "--disable-blink-features=AutomationControlled",
                "--lang=en-IN",
                "--no-first-run",
                "--no-default-browser-check",
            ],
            viewport={"width": 1280, "height": 900},
            locale="en-IN",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        _context = _browser
        _page    = _browser.new_page()
        _apply_stealth(_page)
        print("  [OK] Browser ready.")
    except Exception as e:
        print(f"  [ERR] Chrome start error: {e}")
        _pw = _browser = _context = _page = None

    return _page


def close_login_driver():
    """Browser band karo (cleanup)."""
    global _pw, _browser, _context, _page
    if _browser is not None:
        print("[STOP] Chrome browser band ho raha hai...")
        try:
            _browser.close()
        except Exception:
            pass
    if _pw is not None:
        try:
            _pw.stop()
        except Exception:
            pass
    _page = _context = _browser = _pw = None


# ─────────────────────────────────────────────────────────────────────────────
# Google Login (persistent profile hone par usually skip hoga)
# ─────────────────────────────────────────────────────────────────────────────

def _ensure_login(page) -> bool:
    """Google login check karo — agar logged out ho toh login karo."""
    if not GMAIL_ID or not GMAIL_PASSWORD:
        print("  ⚠ GMAIL_ID/PASSWORD nahi hai — login skip.")
        return False
    try:
        page.goto("https://accounts.google.com", wait_until="domcontentloaded", timeout=20000)
        time.sleep(random.uniform(1.5, 3))

        # Already logged in check
        if page.locator("input[type='email']").count() == 0:
            print("  [OK] Google mein already logged in hai (persistent profile).")
            return True

        print("  [LOGIN] Google login ho raha hai...")
        email_input = page.locator("input[type='email']").first
        for char in GMAIL_ID:
            email_input.type(char, delay=random.randint(50, 120))
        email_input.press("Enter")
        time.sleep(random.uniform(3, 5))

        pw_input = page.wait_for_selector("input[type='password']", timeout=12000)
        for char in GMAIL_PASSWORD:
            pw_input.type(char, delay=random.randint(50, 120))
        pw_input.press("Enter")
        time.sleep(random.uniform(5, 8))

        if "accounts.google.com" in page.url:
            print("  [WARN] CAPTCHA/2FA ho sakta hai -- please browser mein solve karo.")
            print("  [WAIT] 25 seconds wait ho raha hai...")
            time.sleep(25)

        print("  [OK] Login complete.")
        return True
    except Exception as e:
        print(f"  [ERR] Login error: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# AI Overview Extraction
# Google ka AI Overview = multiple web sources ka summarized answer
# CSS selectors frequently change karein — isliye multiple try karte hain
# ─────────────────────────────────────────────────────────────────────────────

# Updated 2024-2025 selectors (most to least reliable order)
_AI_SELECTORS = [
    "div.wDYxhc",
    "div.IVvmub",
    "div.Vkgah",
    "div.p9sGrd",
    "div[jsname='yynole']",
    "div.kno-rdesc span",
    "div.MUxGbd.lyLwlc",
    "span.hgKElc",
    "div.VwiC3b",
    "div.s3v9rd",
]


def _extract_ai_overview(page) -> str:
    """
    Google search results page se AI Overview text nikalo.
    AI Overview asynchronously load hota hai — isliye wait + multi-method.
    """
    print("  [AI] AI Overview dhoondh raha hoon...")

    # AI Overview asynchronously load hota hai -- thoda zyada wait karo
    time.sleep(random.uniform(5, 7))

    found_text = ""

    # Method 1: Known CSS selectors
    for selector in _AI_SELECTORS:
        try:
            els = page.locator(selector).all()
            parts = [el.inner_text().strip() for el in els if el.inner_text().strip()]
            if parts:
                combined = "\n".join(parts[:5])
                if len(combined) > 120:
                    print(f"  [OK] AI Overview mila [{selector}] -- {len(combined)} chars")
                    found_text = combined
                    break
        except Exception:
            continue

    # Method 2: JavaScript — "AI Overview" heading ke baad ka content dhundo
    if not found_text:
        try:
            js_text = page.evaluate("""() => {
                const headings = document.querySelectorAll('h2, h3, [role="heading"]');
                for (const h of headings) {
                    const txt = (h.innerText || '').toLowerCase();
                    if (txt.includes('ai overview') || txt.includes('about this result')) {
                        const container = h.closest(
                            'div[jscontroller], div[data-hveid], div.kno-rdesc, div.wDYxhc, div.IVvmub'
                        ) || h.parentElement;
                        if (container && container.innerText.length > 120) {
                            return container.innerText.slice(0, 3500);
                        }
                    }
                }
                // Fallback: page ke top area ka text lo (approx first 4000 chars minus nav)
                const main = document.querySelector('#main, #rso, div[role="main"]');
                return main ? main.innerText.slice(0, 3000) : '';
            }""")
            if js_text and len(js_text.strip()) > 120:
                print(f"  [OK] AI Overview JS method se mila -- {len(js_text)} chars")
                found_text = js_text.strip()
        except Exception as e:
            print(f"  [WARN] JS extraction error: {e}")

    # Method 3: Knowledge panel
    if not found_text:
        try:
            kp_text = ""
            for sel in ["div.kno-rdesc", "div.kX21rb", "div[data-attrid]"]:
                els = page.locator(sel).all()
                parts = [e.inner_text().strip() for e in els if e.inner_text().strip()]
                kp_text = "\n".join(parts)
                if len(kp_text) > 120:
                    break
            if kp_text:
                print(f"  [OK] Knowledge panel mila -- {len(kp_text)} chars")
                found_text = kp_text
        except Exception:
            pass

    if not found_text:
        print("  [WARN] AI Overview nahi mila is search ke liye.")

    return found_text


# ─────────────────────────────────────────────────────────────────────────────
# Web page text extraction helpers
# ─────────────────────────────────────────────────────────────────────────────

def _get_result_links(page, max_links: int = 3) -> list:
    """
    Google search page se top result links nikalo.
    JS-based extraction (CSS :has unreliable in headless/playwright).
    """
    links = []
    try:
        # JS se directly anchor tags nikalo jo h3 contain karte hain
        time.sleep(2)  # results render hone ka wait
        js_links = page.evaluate("""
            () => {
                const anchors = document.querySelectorAll('a');
                const results = [];
                for (const a of anchors) {
                    if (a.querySelector('h3') && a.href &&
                        !a.href.includes('google.com') &&
                        a.href.startsWith('http') &&
                        !results.includes(a.href)) {
                        results.push(a.href);
                    }
                    if (results.length >= 5) break;
                }
                return results;
            }
        """)
        links = (js_links or [])[:max_links]
    except Exception as e:
        print(f"  [WARN] Links extract error: {e}")
    return links


def _fetch_text_requests(url: str, max_chars: int = 5000) -> str:
    """requests + BeautifulSoup se page text nikalo (fast, no browser)."""
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-IN,en;q=0.9",
        }
        resp = requests.get(url, headers=headers, timeout=12)
        resp.raise_for_status()

        # BeautifulSoup se clean text
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, "lxml")
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()
            text = soup.get_text(separator="\n", strip=True)
        except ImportError:
            # Fallback: crude regex strip
            text = re.sub(r"<[^>]+>", " ", resp.text)
            text = re.sub(r"\s+", " ", text).strip()

        return text[:max_chars]
    except Exception as e:
        print(f"    [WARN] requests fetch error: {e}")
        return ""


def _fetch_text_browser(page, url: str, max_chars: int = 5000) -> str:
    """Browser se page text nikalo (agar requests block ho)."""
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=15000)
        time.sleep(random.uniform(2, 3.5))
        text = page.evaluate("document.body.innerText")
        return (text or "")[:max_chars]
    except Exception as e:
        print(f"    [WARN] Browser fetch error: {e}")
        return ""


# ─────────────────────────────────────────────────────────────────────────────
# SerpAPI fallback
# ─────────────────────────────────────────────────────────────────────────────

def _serp_search(query: str, limit: int = 3):
    """SerpAPI se Google results lo — AI Overview bhi mil sakta hai."""
    if not SERP_API_KEY:
        return []
    try:
        params = {
            "engine": "google",
            "q": query,
            "api_key": SERP_API_KEY,
            "num": limit,
            "google_domain": "google.com",   # .com for English results
            "gl": "in",                        # India geolocation
            "hl": "en",                        # English language
            "lr": "lang_en",                   # English pages only
            "safe": "off",
        }
        resp = requests.get("https://serpapi.com/search.json", params=params, timeout=15)
        data = resp.json()

        results = []

        # SerpAPI ka AI Overview check
        ai = data.get("ai_overview", {})
        snippets = ai.get("snippets", []) if ai else []
        if snippets:
            ai_text = "\n".join(s.get("content", "") for s in snippets if s.get("content"))
            if len(ai_text) > 100:
                print(f"  [OK] SerpAPI AI Overview mila -- {len(ai_text)} chars")
                results.append(("__AI__", ai_text))

        # Organic links
        for r in data.get("organic_results", []):
            link = r.get("link")
            if link:
                results.append(("link", link))

        return results[:limit + 1]
    except Exception as e:
        print(f"  [WARN] SerpAPI error: {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# DuckDuckGo fallback
# ─────────────────────────────────────────────────────────────────────────────

def _ddg_links(query: str, limit: int = 3) -> list:
    """DuckDuckGo HTML API se links lo (no key, no browser)."""
    try:
        # Module ya script dono se import ho sake
        try:
            from gettinglinks.duckduckgo import get_duckduckgo_links
        except ModuleNotFoundError:
            from duckduckgo import get_duckduckgo_links
        links = get_duckduckgo_links(query, limit=limit)
        print(f"  [DDG] DuckDuckGo se {len(links)} links mile.")
        return links
    except Exception as e:
        print(f"  [WARN] DuckDuckGo error: {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# MAIN PUBLIC FUNCTION
# ─────────────────────────────────────────────────────────────────────────────

def _do_browser_search(query: str, num_results: int) -> str:
    """
    Actual browser search logic -- thread mein run hoga (asyncio se bahar).
    """
    page = _get_page()
    if not page:
        return ""

    extracted = ""
    try:
        print(f"\n  [SEARCH] Google search: '{query}'")

        enc = requests.utils.quote(query)
        page.goto(
            f"https://www.google.com/search?q={enc}&hl=en&gl=in",
            wait_until="domcontentloaded", timeout=20000
        )
        time.sleep(random.uniform(3, 4))

        # CAPTCHA check
        if "sorry" in page.url or "captcha" in page.url.lower():
            print("  [WARN] Google ne CAPTCHA diya! Browser mein solve karo...")
            time.sleep(60)
            if "sorry" in page.url:
                raise Exception("Google CAPTCHA block.")

        # AI Overview extract karo
        ai_text = _extract_ai_overview(page)
        if ai_text:
            extracted += "--- Google AI Overview (Multi-Source Summary) ---\n"
            extracted += ai_text + "\n"
            extracted += "-------------------------------------------------\n\n"

        # Top links bhi lo
        links = _get_result_links(page, max_links=num_results)
        print(f"  [LINKS] Google se {len(links)} links mile.")

        for i, url in enumerate(links, 1):
            print(f"  [{i}/{len(links)}] Fetching: {url[:80]}...")
            text = _fetch_text_requests(url)
            if not text:
                text = _fetch_text_browser(page, url)
            if text:
                extracted += f"\n--- Source {i}: {url} ---\n{text}\n"
                print(f"    [OK] {len(text)} chars.")

    except Exception as e:
        print(f"  [ERR] Browser search error: {e}")

    return extracted


def search_and_extract_gemini_and_links(query: str, num_results: int = 2) -> str:
    """
    Search karo aur text extract karo.

    Fallback chain:
      1. Gemini Browser  -> gemini.google.com (NO CAPTCHA, best AI response)
      2. Google Browser  -> Google AI Overview + web links
      3. SerpAPI         -> links -> requests se text
      4. DuckDuckGo      -> links -> requests se text
    """
    extracted = ""

    # -- LAYER 1: Gemini Browser (Primary -- no CAPTCHA) ----------------------
    print(f"  [Gemini Browser] Searching...")
    try:
        from gettinglinks.gemini_browser_search import search_with_gemini, close_gemini_browser
        gemini_text = search_with_gemini(query)
        if gemini_text and len(gemini_text.strip()) > 80:
            extracted = "--- Gemini AI Response ---\n" + gemini_text.strip() + "\n--------------------------\n"
        else:
            close_gemini_browser()
    except Exception as e:
        print(f"  [WARN] Gemini browser error: {e}")
        try:
            from gettinglinks.gemini_browser_search import close_gemini_browser
            close_gemini_browser()
        except Exception:
            pass

    # -- LAYER 2: Google Browser (Fallback) -----------------------------------
    if not extracted:
        print("\n  [WARN] Gemini se data nahi mila -- Google browser try kar raha hoon...")
        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(_do_browser_search, query, num_results)
                extracted = future.result(timeout=120)
        except FutureTimeout:
            print("  [WARN] Google browser timeout (120s).")
        except Exception as e:
            print(f"  [ERR] Google browser thread error: {e}")

    # -- LAYER 3: SerpAPI -----------------------------------------------------
    if not extracted:
        print("\n  [WARN] Browser se kuch nahi mila -- SerpAPI try kar raha hoon...")
        for item_type, item_val in _serp_search(query, limit=num_results):
            if item_type == "__AI__":
                extracted += "--- SerpAPI AI Overview ---\n" + item_val + "\n---\n\n"
            else:
                text = _fetch_text_requests(item_val)
                if text:
                    extracted += f"\n--- Source: {item_val} ---\n{text}\n"

    # -- LAYER 4: DuckDuckGo --------------------------------------------------
    if not extracted:
        print("\n  [WARN] SerpAPI bhi fail -- DuckDuckGo try kar raha hoon...")
        for url in _ddg_links(query, limit=num_results):
            text = _fetch_text_requests(url)
            if text:
                extracted += f"\n--- Source: {url} ---\n{text}\n"

    if not extracted:
        print("  [ERR] Koi bhi source se data nahi mila.")

    return extracted



# ─────────────────────────────────────────────────────────────────────────────
# Quick test
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    result = search_and_extract_gemini_and_links("Golghar Patna Bihar history", num_results=1)
    print("\n" + "=" * 60)
    print(f"TOTAL EXTRACTED: {len(result)} chars")
    print("=" * 60)
    # ASCII-safe print for Windows terminal
    safe = result[:2000].encode("ascii", errors="replace").decode("ascii")
    print(safe)
    close_login_driver()
