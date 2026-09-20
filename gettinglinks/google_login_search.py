"""
google_login_search.py

Playwright se Chrome browser automate karo, Google pe search karo,
AI Overview extract karo (multi-source summary) aur web links ka text lo.

Strategy:
  PRIMARY  → Chrome (Playwright + stealth) → Google AI Overview
  FALLBACK1 → Top web links content (Chrome se hi)
  FALLBACK2 → SerpAPI → AI Overview ya links → requests se text
  FALLBACK3 → DuckDuckGo → links → requests se text

Thread Architecture:
  Playwright Sync API is bound to a single thread. To avoid thread conflicts,
  broken pipes, and profile directory locking collisions when called from GUI
  or sequential loops, a dedicated worker thread manages the browser session.
"""

import os
import re
import time
import queue
import random
import threading
import requests
from urllib.parse import urlparse
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()
GMAIL_ID       = os.getenv("GMAIL_ID", "")
GMAIL_PASSWORD = os.getenv("GMAIL_PASSWORD", "")
SERP_API_KEY   = os.getenv("SERP_API_KEY", "")

# ─────────────────────────────────────────────────────────────────────────────
# Profile setup
# Dedicated playwright_profile folder -- persistent session for cookies
# ─────────────────────────────────────────────────────────────────────────────

_PW_PROFILE_DIR = str(Path(__file__).resolve().parent.parent / "playwright_profile")
os.makedirs(_PW_PROFILE_DIR, exist_ok=True)

# ─────────────────────────────────────────────────────────────────────────────
# AI Overview Extraction Selectors
# ─────────────────────────────────────────────────────────────────────────────

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
    time.sleep(random.uniform(4.5, 6.0))

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

    # Method 2: JavaScript — "AI Overview" heading ke baad ka container dhundo
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


def _get_result_links(page, max_links: int = 3) -> list:
    """Google search page se top result links nikalo, excluding blocked/social/heavy domains."""
    links = []
    try:
        time.sleep(2)
        js_links = page.evaluate("""
            () => {
                const anchors = document.querySelectorAll('a');
                const results = [];
                const blockedDomains = [
                    'google.', 'tripadvisor.', 'facebook.com', 'instagram.com',
                    'twitter.com', 'x.com', 'linkedin.com', 'pinterest.com',
                    'youtube.com', 'maps.google'
                ];
                for (const a of anchors) {
                    if (a.querySelector('h3') && a.href && a.href.startsWith('http')) {
                        const hrefLower = a.href.toLowerCase();
                        const isBlocked = blockedDomains.some(d => hrefLower.includes(d));
                        if (!isBlocked && !results.includes(a.href)) {
                            results.push(a.href);
                        }
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
    """requests + BeautifulSoup se page text nikalo."""
    try:
        domain = urlparse(url).netloc.lower()
        blocked_domains = [
            "tripadvisor.", "facebook.com", "instagram.com",
            "twitter.com", "x.com", "youtube.com", "linkedin.com", "pinterest.com"
        ]
        if any(b in domain for b in blocked_domains):
            return ""

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-IN,en;q=0.9",
        }
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()

        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, "lxml")
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()
            text = soup.get_text(separator="\n", strip=True)
        except ImportError:
            text = re.sub(r"<[^>]+>", " ", resp.text)
            text = re.sub(r"\s+", " ", text).strip()

        return text[:max_chars]
    except Exception as e:
        print(f"    [WARN] requests fetch error: {e}")
        return ""


def _fetch_text_browser(page, url: str, max_chars: int = 5000) -> str:
    """Browser se page text nikalo."""
    try:
        domain = urlparse(url).netloc.lower()
        blocked_domains = [
            "tripadvisor.", "facebook.com", "instagram.com",
            "twitter.com", "x.com", "youtube.com", "linkedin.com", "pinterest.com"
        ]
        if any(b in domain for b in blocked_domains):
            return ""

        page.goto(url, wait_until="domcontentloaded", timeout=12000)
        time.sleep(random.uniform(2, 3.5))
        text = page.evaluate("document.body.innerText")
        return (text or "")[:max_chars]
    except Exception as e:
        print(f"    [WARN] Browser fetch error: {e}")
        return ""


# ─────────────────────────────────────────────────────────────────────────────
# Login Verification Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _is_logged_in_verified(page) -> bool:
    """
    Check karta hai ki Google Account genuinely logged in hai ya nahi.
    False positive na aaye isliye strictly elements + URL check karta hai.
    """
    try:
        curr_url = (page.url or "").lower()
        u = urlparse(curr_url)
        host = (u.hostname or "").lower()

        # 1. Agar accounts.google.com par hai -> Definitely NOT logged in yet
        if "accounts.google" in host:
            return False

        # 2. Marketing / informational page -> NOT logged in
        if "account/about" in curr_url or "accounts.google.com/servicelogin" in curr_url:
            return False

        # 3. Google search ya home page par check
        if "google." in host:
            # Check for logged-in profile avatar
            profile_count = page.locator(
                "a[aria-label*='Google Account'], a[aria-label*='Google खाता'], "
                "a.gb_d, img.gb_d, a[href*='SignOutOptions']"
            ).count()

            # Check for Sign in button
            signin_count = page.locator(
                "a[href*='ServiceLogin'], a[href*='accounts.google.com/signin']"
            ).count()

            if profile_count > 0 and signin_count == 0:
                return True

        # 4. myaccount page direct
        if host == "myaccount.google.com" and "signin" not in curr_url:
            return True

    except Exception:
        pass
    return False



# ─────────────────────────────────────────────────────────────────────────────
# Single Dedicated Browser Worker Thread
# ─────────────────────────────────────────────────────────────────────────────

_task_queue = queue.Queue()
_worker_thread = None
_worker_lock = threading.Lock()
_login_checked = False


def _is_captcha_page(page) -> bool:
    """Detect if the current page is a Google CAPTCHA or 'sorry' page."""
    try:
        url_lower = (page.url or "").lower()
        if "sorry" in url_lower or "captcha" in url_lower:
            return True
        title_lower = (page.title() or "").lower()
        if "unusual traffic" in title_lower or "captcha" in title_lower:
            return True
    except Exception:
        pass
    return False


def _execute_page_search(page, query: str, num_results: int) -> tuple[str, bool]:
    """
    Page par Google search run karo aur text extract karo.
    Returns: (extracted_text, had_captcha_timeout)
    """
    extracted = ""
    had_captcha_timeout = False
    try:
        print(f"\n  [SEARCH] Google search: '{query}'")
        enc = requests.utils.quote(query)
        page.goto(
            f"https://www.google.com/search?q={enc}&hl=en&gl=in",
            wait_until="domcontentloaded",
            timeout=25000
        )
        time.sleep(random.uniform(2.5, 3.5))

        # CAPTCHA check
        if _is_captcha_page(page):
            print("\n" + "=" * 65)
            print("  ⚠️ GOOGLE CAPTCHA DETECTED")
            print("  👉 Agar aap chahein toh 10s me solve kar sakte hain, warna automatic skip ho jayega...")
            print("=" * 65)
            captcha_solved = False
            for _ in range(5):  # 5 * 2s = 10 seconds max
                time.sleep(2)
                if not _is_captcha_page(page):
                    print("  ✅ CAPTCHA solve ho gaya! Search continue kar rahe hain...")
                    captcha_solved = True
                    time.sleep(1.5)
                    break

            if not captcha_solved:
                print("  ⏩ CAPTCHA 10s me solve nahi hua. Browser session reset karenge aur fallback par move karenge...\n")
                return "", True

        # AI Overview extract karo
        ai_text = _extract_ai_overview(page)
        if ai_text:
            extracted += "--- Google AI Overview (Multi-Source Summary) ---\n"
            extracted += ai_text + "\n"
            extracted += "-------------------------------------------------\n\n"

        # Top web links bhi lo
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

    return extracted, False


def _find_chrome_path() -> str:
    possible_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    ]
    for p in possible_paths:
        if os.path.exists(p):
            return p
    return "chrome"


def _launch_native_chrome_login():
    """
    Genuine Chrome window open karta hai taaki Google ka
    'This browser or app may not be secure' error na aaye.
    User aaram se login karke window band karega.
    """
    import subprocess
    chrome_path = _find_chrome_path()
    print("\n" + "=" * 74)
    print("  🔑 GOOGLE ACCOUNT LOGIN SETUP (Sirf 1 baar karna hai)")
    print("=" * 74)
    print("  Google automated browsers me direct login block karta hai ('Not secure').")
    print("  Isliye genuine Google Chrome window open ho rahi hai.")
    print("  👉 Kripya apna Email, Password aur 2FA daal kar login complete kijiye.")
    print("  👉 Login complete hone ke baad Chrome window ko CLOSE (band) kar dijiye!")
    print("=" * 74 + "\n")

    cmd = [
        chrome_path,
        f"--user-data-dir={_PW_PROFILE_DIR}",
        "--no-first-run",
        "--no-default-browser-check",
        "https://accounts.google.com/signin"
    ]
    try:
        proc = subprocess.Popen(cmd)
        proc.wait()
        print("\n  🎉 Chrome window close ho gayi! Session 'playwright_profile' me save ho gaya.\n")
    except Exception as e:
        print(f"  [ERR] Native Chrome launch error: {e}")


def _browser_worker_loop():
    """
    Dedicated worker thread loop.
    Har Playwright command isi ek thread me run hoti hai.
    Persistent context open rehta hai across all sheet row repairs / place searches.
    Includes proactive session recycling (every 8 searches) and reactive CAPTCHA reset.
    """
    pw = None
    browser = None
    page = None
    searches_since_recycle = 0

    def close_all():
        nonlocal pw, browser, page
        if page is not None:
            try:
                page.close()
            except Exception:
                pass
            page = None
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass
            browser = None
        if pw is not None:
            try:
                pw.stop()
            except Exception:
                pass
            pw = None

    def get_or_create_page(allow_native_login: bool = True):
        nonlocal pw, browser, page
        global _login_checked
        if page is not None:
            try:
                _ = page.title()
                return page
            except Exception:
                close_all()

        print("[Browser] Playwright Chromium start ho raha hai...")
        try:
            from playwright.sync_api import sync_playwright

            try:
                from playwright_stealth import Stealth
                _stealth_obj = Stealth()
                apply_stealth = lambda pg: _stealth_obj.apply_stealth_sync(pg)
            except ImportError:
                try:
                    from playwright_stealth import stealth_sync
                    apply_stealth = stealth_sync
                except ImportError:
                    apply_stealth = lambda pg: None

            pw = sync_playwright().start()
            browser = pw.chromium.launch_persistent_context(
                user_data_dir=_PW_PROFILE_DIR,
                channel="chrome",
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
            page = browser.new_page()
            apply_stealth(page)
            print("  [OK] Browser ready.")

            # Login status check
            if not _login_checked:
                print("🔍 Checking Google Account login status...")
                try:
                    page.goto("https://www.google.com", wait_until="domcontentloaded", timeout=20000)
                    time.sleep(2)
                except Exception:
                    pass

                if _is_logged_in_verified(page):
                    print("  ✅ [Case 2] Google Account already logged in hai! Seedha Search shuru kar rahe hain...\n")
                    _login_checked = True
                elif allow_native_login:
                    # User not logged in yet -> Close Playwright and open genuine Chrome for 1-time login
                    close_all()
                    _launch_native_chrome_login()
                    _login_checked = True
                    # Re-open Playwright with the newly saved session
                    return get_or_create_page(allow_native_login=False)
                else:
                    print("  ⚠ Login skip ho gaya. Search continue kar rahe hain...\n")
                    _login_checked = True

            return page
        except Exception as e:
            print(f"  [ERR] Chrome start error: {e}")
            close_all()
            return None

    while True:
        task = _task_queue.get()
        if task is None:
            close_all()
            _task_queue.task_done()
            break

        cmd, args, result_box, done_event = task
        try:
            if cmd == "search":
                query, num_results = args

                # --- PROACTIVE SESSION RECYCLING ---
                # Google rate-limits automated rapid requests (~8-10 searches).
                # Re-cycling the browser clears socket connections and temporary bot scoring.
                if searches_since_recycle >= 8:
                    print(f"\n🔄 [Session Recycle] {searches_since_recycle} searches complete. Closing browser session to avoid rate limits & refreshing...")
                    close_all()
                    time.sleep(random.uniform(4.0, 6.0))
                    searches_since_recycle = 0

                p = get_or_create_page()
                if p:
                    search_res, had_captcha_timeout = _execute_page_search(p, query, num_results)
                    result_box["result"] = search_res

                    if had_captcha_timeout:
                        print("🛑 [Browser Reset] CAPTCHA detected on Google. Closing browser immediately so next search starts clean...")
                        close_all()
                        time.sleep(random.uniform(4.0, 6.0))
                        searches_since_recycle = 0
                    else:
                        searches_since_recycle += 1
                else:
                    result_box["error"] = "Browser could not be initialized."
            elif cmd == "close":
                close_all()
                searches_since_recycle = 0
                result_box["result"] = "closed"
        except Exception as e:
            result_box["error"] = str(e)
        finally:
            done_event.set()
            _task_queue.task_done()


def _ensure_worker_started():
    """Worker thread ensure karo ki running hai."""
    global _worker_thread
    with _worker_lock:
        if _worker_thread is None or not _worker_thread.is_alive():
            _worker_thread = threading.Thread(
                target=_browser_worker_loop,
                daemon=True,
                name="PlaywrightBrowserWorker"
            )
            _worker_thread.start()


def close_login_driver():
    """Browser band karo (cleanup)."""
    global _worker_thread
    with _worker_lock:
        if _worker_thread is not None and _worker_thread.is_alive():
            print("[STOP] Chrome browser band ho raha hai...")
            done_event = threading.Event()
            result_box = {}
            _task_queue.put(("close", None, result_box, done_event))
            done_event.wait(timeout=6)


# ─────────────────────────────────────────────────────────────────────────────
# SerpAPI fallback
# ─────────────────────────────────────────────────────────────────────────────

def _serp_search(query: str, limit: int = 3):
    """SerpAPI se Google results lo."""
    if not SERP_API_KEY:
        return []
    try:
        params = {
            "engine": "google",
            "q": query,
            "api_key": SERP_API_KEY,
            "num": limit,
            "google_domain": "google.com",
            "gl": "in",
            "hl": "en",
            "lr": "lang_en",
            "safe": "off",
        }
        resp = requests.get("https://serpapi.com/search.json", params=params, timeout=15)
        data = resp.json()

        results = []
        ai = data.get("ai_overview", {})
        snippets = ai.get("snippets", []) if ai else []
        if snippets:
            ai_text = "\n".join(s.get("content", "") for s in snippets if s.get("content"))
            if len(ai_text) > 100:
                print(f"  [OK] SerpAPI AI Overview mila -- {len(ai_text)} chars")
                results.append(("__AI__", ai_text))

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
    """DuckDuckGo HTML API se links lo."""
    try:
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

def search_and_extract_gemini_and_links(query: str, num_results: int = 2) -> str:
    """
    Search karo aur text extract karo.

    Fallback chain:
      1. Google Browser (Dedicated worker) -> Google AI Overview + web links
      2. SerpAPI Fallback                  -> links -> requests se text
      3. DuckDuckGo Fallback               -> links -> requests se text
    """
    extracted = ""

    # -- LAYER 1: Google Browser (Live Search + AI Overview) -----------------
    print(f"\n  🌐 [Live Google Search] Searching with Google AI Overview...")
    try:
        _ensure_worker_started()
        done_event = threading.Event()
        result_box = {"result": "", "error": None}
        _task_queue.put(("search", (query, num_results), result_box, done_event))

        # First query may need manual login if not logged in (330s max)
        timeout = 330 if not _login_checked else 75
        if not done_event.wait(timeout=timeout):
            print(f"  [WARN] Google browser search timed out ({timeout}s).")
        else:
            if result_box.get("error"):
                print(f"  [ERR] Browser error: {result_box['error']}")
            else:
                extracted = result_box.get("result", "")
    except Exception as e:
        print(f"  [ERR] Browser runner error: {e}")

    # -- LAYER 2: SerpAPI Fallback --------------------------------------------
    if not extracted:
        print("\n  [WARN] Browser se data nahi mila -- SerpAPI try kar raha hoon...")
        for item_type, item_val in _serp_search(query, limit=num_results):
            if item_type == "__AI__":
                extracted += "--- SerpAPI AI Overview ---\n" + item_val + "\n---\n\n"
            else:
                text = _fetch_text_requests(item_val)
                if text:
                    extracted += f"\n--- Source: {item_val} ---\n{text}\n"

    # -- LAYER 3: DuckDuckGo Fallback -----------------------------------------
    if not extracted:
        print("\n  [WARN] SerpAPI bhi fail -- DuckDuckGo try kar raha hoon...")
        for url in _ddg_links(query, limit=num_results):
            text = _fetch_text_requests(url)
            if text:
                extracted += f"\n--- Source: {url} ---\n{text}\n"

    if not extracted:
        print("  [ERR] Koi bhi source se data nahi mila.")

    return extracted


if __name__ == "__main__":
    result = search_and_extract_gemini_and_links("Golghar Patna Bihar history", num_results=1)
    print("\n" + "=" * 60)
    print(f"TOTAL EXTRACTED: {len(result)} chars")
    print("=" * 60)
    safe = result[:2000].encode("ascii", errors="replace").decode("ascii")
    print(safe)
    close_login_driver()
