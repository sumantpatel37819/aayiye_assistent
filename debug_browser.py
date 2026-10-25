"""
Debug script — search ke baad page screenshot lo
"""
import sys, time, random
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from gettinglinks.chrome_config import find_chrome, chrome_user_data_dir, assistant_profile_dir

from playwright.sync_api import sync_playwright

# Cookie sync
import os, shutil
REAL_CHROME = str(chrome_user_data_dir())
PW_PROFILE  = str(assistant_profile_dir())
os.makedirs(os.path.join(PW_PROFILE, "Default", "Network"), exist_ok=True)

for src, dst in [
    (os.path.join(REAL_CHROME, "Default", "Cookies"),            os.path.join(PW_PROFILE, "Default", "Cookies")),
    (os.path.join(REAL_CHROME, "Default", "Network", "Cookies"), os.path.join(PW_PROFILE, "Default", "Network", "Cookies")),
]:
    if not os.path.isfile(src):
        continue
    try:
        with open(src, 'rb') as f:
            data = f.read()
        with open(dst, 'wb') as f:
            f.write(data)
        print(f"Copied: {os.path.basename(src)}")
    except PermissionError:
        if sys.platform != "win32":
            print(f"SKIP (permission denied): {src}")
            continue
        import ctypes, ctypes.wintypes
        handle = ctypes.windll.kernel32.CreateFileW(
            src, 0x80000000, 0x00000001 | 0x00000002, None, 3, 0, None)
        if handle and handle != -1:
            size = os.path.getsize(src)
            buf  = ctypes.create_string_buffer(size)
            read = ctypes.wintypes.DWORD(0)
            ctypes.windll.kernel32.ReadFile(handle, buf, size, ctypes.byref(read), None)
            ctypes.windll.kernel32.CloseHandle(handle)
            with open(dst, 'wb') as f:
                f.write(buf.raw[:read.value])
            print(f"Copied (locked): {os.path.basename(src)}")
        else:
            print(f"SKIP (could not open): {os.path.basename(src)}")

pw = sync_playwright().start()
br = pw.chromium.launch_persistent_context(
    user_data_dir=PW_PROFILE,
    executable_path=find_chrome(),
    headless=False,
    args=["--start-maximized", "--disable-blink-features=AutomationControlled", "--no-first-run"],
    viewport={"width": 1280, "height": 900},
    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
)
page = br.new_page()

# Google homepage
page.goto("https://www.google.com", wait_until="domcontentloaded", timeout=20000)
time.sleep(2)
page.screenshot(path="dbg_01_home.png")
print("Home URL:", page.url, "| Title:", page.title())

# Search
try:
    sb = page.wait_for_selector("textarea[name='q'], input[name='q']", timeout=8000)
    sb.fill("Golghar Patna Bihar history")
    sb.press("Enter")
    time.sleep(5)
    page.screenshot(path="dbg_02_results.png")
    print("Results URL:", page.url)
    print("Results Title:", page.title())
except Exception as e:
    print("Search error:", e)
    page.screenshot(path="dbg_02_error.png")

# Check URL for CAPTCHA
if "sorry" in page.url:
    print("!!! CAPTCHA PAGE !!!")
else:
    # What elements exist on results page
    counts = page.evaluate("""() => ({
        h3Count: document.querySelectorAll('h3').length,
        anchorH3: Array.from(document.querySelectorAll('a')).filter(a => a.querySelector('h3')).length,
        bodyLen:  document.body.innerText.length,
        firstH3: document.querySelector('h3') ? document.querySelector('h3').innerText.slice(0,100) : 'none',
        hasAI:   document.body.innerHTML.includes('AI Overview'),
        wDYxhc:  !!document.querySelector('div.wDYxhc'),
        IVvmub:  !!document.querySelector('div.IVvmub'),
        rsoLen:  document.querySelector('#rso') ? document.querySelector('#rso').innerText.length : 0,
    })""")
    for k, v in counts.items():
        print(f"  {k}: {v}")

br.close()
pw.stop()
print("Done. Check dbg_01_home.png and dbg_02_results.png")
