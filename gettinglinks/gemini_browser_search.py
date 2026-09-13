"""
gemini_browser_search.py

Real Chrome browser mein Gemini kholke search karo.

Flow:
  1. Playwright Chromium window mein gemini.google.com kholo
  2. Query type karo
  3. Gemini ka response wait karo (streaming detect)
  4. Response text extract karo aur return karo

Note: ThreadPoolExecutor mein run hota hai (asyncio compatible).
"""

import os
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# Profile setup
# ─────────────────────────────────────────────────────────────────────────────

_PW_PROFILE_DIR = str(Path(__file__).resolve().parent.parent / "playwright_profile")
os.makedirs(_PW_PROFILE_DIR, exist_ok=True)

GEMINI_URL = "https://gemini.google.com/app"

_pw      = None
_browser = None
_page    = None


def _get_page():
    """Playwright Chromium kholo — Gemini ke liye."""
    global _pw, _browser, _page

    if _page is not None:
        try:
            _ = _page.title()
            return _page
        except Exception:
            _page = _browser = _pw = None

    print("[Browser] Playwright Chromium start ho raha hai (Gemini ke liye)...")
    try:
        from playwright.sync_api import sync_playwright

        try:
            from playwright_stealth import Stealth
            _so = Stealth()
            _apply_stealth = lambda pg: _so.apply_stealth_sync(pg)
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
                "--no-first-run",
                "--no-default-browser-check",
            ],
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        _page = _browser.new_page()
        _apply_stealth(_page)
        print("  [OK] Browser ready.")
        return _page
    except Exception as e:
        print(f"  [ERR] Browser start error: {e}")
        _pw = _browser = _page = None
        return None


def close_gemini_browser():
    """Browser cleanup."""
    global _pw, _browser, _page
    if _browser is not None:
        try:
            _browser.close()
        except Exception:
            pass
    if _pw is not None:
        try:
            _pw.stop()
        except Exception:
            pass
    _page = _browser = _pw = None


# ─────────────────────────────────────────────────────────────────────────────
# Selectors
# ─────────────────────────────────────────────────────────────────────────────

_INPUT_SELECTORS = [
    "div[contenteditable='true'][role='textbox']",
    "rich-textarea div[contenteditable='true']",
    "div.ql-editor[contenteditable='true']",
    "div[contenteditable='true']",
    "textarea",
]

_RESPONSE_SELECTORS = [
    "model-response .markdown",
    "model-response",
    "message-content .markdown",
    ".response-container .markdown",
    "div.markdown",
]

_STOP_BTN_SELECTORS = [
    "button[aria-label='Stop generating']",
    "button[aria-label*='Stop']",
]


def _wait_for_response_complete(page, max_wait: int = 45) -> None:
    """Stop button gayab hone tak wait karo (response complete)."""
    # Pehle stop button aane ka wait (3s)
    for _ in range(6):
        for sel in _STOP_BTN_SELECTORS:
            try:
                if page.locator(sel).count() > 0:
                    break
            except Exception:
                pass
        else:
            time.sleep(0.5)
            continue
        break

    # Ab stop button gayab hone ka wait
    for _ in range(max_wait * 2):
        for sel in _STOP_BTN_SELECTORS:
            try:
                if page.locator(sel).count() > 0:
                    time.sleep(0.5)
                    break
            except Exception:
                pass
        else:
            time.sleep(1.5)
            return

    time.sleep(1)  # Final settle


def _extract_response(page) -> str:
    """Gemini response text extract karo."""
    # Method 1: Known selectors
    for sel in _RESPONSE_SELECTORS:
        try:
            els = page.locator(sel).all()
            texts = [el.inner_text().strip() for el in els if len(el.inner_text().strip()) > 30]
            if texts:
                combined = "\n\n".join(texts[-2:])
                if len(combined) > 100:
                    print(f"  [OK] Gemini response [{sel}] -- {len(combined)} chars")
                    return combined
        except Exception:
            continue

    # Method 2: JS
    try:
        js = page.evaluate("""() => {
            const rs = document.querySelectorAll('model-response, .model-response');
            if (rs.length > 0) return rs[rs.length-1].innerText || '';
            const main = document.querySelector('main, [role="main"]');
            if (main) return main.innerText || '';
            return '';
        }""")
        if js and len(js.strip()) > 100:
            print(f"  [OK] Gemini response (JS) -- {len(js)} chars")
            return js.strip()
    except Exception:
        pass

    print("  [WARN] Gemini response selectors fail ho gaye.")
    return ""


def _gemini_search_in_thread(query: str) -> str:
    """Browser thread: Gemini pe jao, query type karo, response lo."""
    page = _get_page()
    if not page:
        return ""

    try:
        print(f"  [Gemini] gemini.google.com pe ja raha hoon...")
        page.goto(GEMINI_URL, wait_until="domcontentloaded", timeout=30000)
        time.sleep(3)

        # Login check (only if Sign in button is actually visible)
        try:
            sign_in = page.locator("button:has-text('Sign in'), a:has-text('Sign in')").first
            if sign_in.is_visible(timeout=2000):
                print("  [INFO] Visible Sign in button mila -- click kar raha hoon...")
                sign_in.click(timeout=5000)
                time.sleep(5)
                if page.locator("input[type='email']").first.is_visible(timeout=2000):
                    print("  [WAIT] Google login required -- 60s manual login karo...")
                    time.sleep(60)
        except Exception:
            pass

        # Text input dhundo
        input_el = None
        for sel in _INPUT_SELECTORS:
            try:
                el = page.locator(sel).first
                if el.is_visible(timeout=3000):
                    input_el = el
                    print(f"  [OK] Input mila [{sel}]")
                    break
            except Exception:
                continue

        if not input_el:
            print("  [ERR] Gemini text input nahi mila -- screenshot le raha hoon")
            page.screenshot(path="gemini_debug.png")
            return ""

        # Query type karo
        input_el.click()
        time.sleep(0.5)
        input_el.press("Control+a")
        time.sleep(0.2)
        try:
            input_el.fill(query)
        except Exception:
            page.keyboard.type(query, delay=15)
        time.sleep(0.5)

        # Submit
        input_el.press("Enter")
        print(f"  [Gemini] Query submit: '{query[:70]}...' " if len(query) > 70 else f"  [Gemini] Query submit: '{query}'")

        # Wait for complete
        print("  [Gemini] Response generate ho raha hai...")
        _wait_for_response_complete(page)

        # Extract
        return _extract_response(page)

    except Exception as e:
        print(f"  [ERR] Gemini error: {e}")
        return ""


def search_with_gemini(query: str) -> str:
    """
    PUBLIC: Gemini browser se search karo (asyncio safe).
    Returns extracted response text.
    """
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_gemini_search_in_thread, query)
            return future.result(timeout=120)
    except FutureTimeout:
        print("  [WARN] Gemini timeout (120s).")
        return ""
    except Exception as e:
        print(f"  [ERR] Gemini thread error: {e}")
        return ""
