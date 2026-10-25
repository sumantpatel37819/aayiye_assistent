"""
login_google.py

Google automated browsers (Playwright/Selenium) me direct login block karta hai:
"This browser or app may not be secure"

Is script se genuine Google Chrome khulta hai (bina kisi automation/Playwright flags ke).
Aap aaram se apna Google Account login aur 2FA kar sakte hain.
Jaise hi login ho jaye, bas Chrome window ko BAND (close) kar dijiye.
Cookies 'playwright_profile' me permanently save ho jayengi!
"""

import os
import sys
import time
import subprocess
from pathlib import Path
from gettinglinks.chrome_config import assistant_profile_dir

PROFILE_DIR = str(assistant_profile_dir())
os.makedirs(PROFILE_DIR, exist_ok=True)

def find_chrome() -> str:
    from gettinglinks.chrome_config import find_chrome as locate_chrome
    return locate_chrome()


def launch_login_chrome():
    chrome_path = find_chrome()
    print("=" * 72)
    print("  🔑 GOOGLE ACCOUNT LOGIN SETUP (Sirf 1 baar karna hai)")
    print("=" * 72)
    print("  1. Abhi genuine Google Chrome window khulegi.")
    print("  2. Apna Google Email, Password aur 2FA enter karke login complete kijiye.")
    print("  3. Login hone ke baad, bas Chrome window ko CLOSE (band) kar dijiye.")
    print("=" * 72 + "\n")

    cmd = [
        chrome_path,
        f"--user-data-dir={PROFILE_DIR}",
        "--no-first-run",
        "--no-default-browser-check",
        "https://accounts.google.com/signin"
    ]

    print(f"🚀 Launching Chrome: {chrome_path}")
    proc = subprocess.Popen(cmd)

    print("\n⏳ Chrome khul gaya hai. Login karne ke baad Chrome window ko band kar dijiye...")
    proc.wait()

    print(f"\n🎉 Chrome close ho gaya! Login session save ho gaya: {PROFILE_DIR}")
    print("Ab aap aaram se apna chatbot ya sheet repair run kar sakte hain!\n")

if __name__ == "__main__":
    launch_login_chrome()
