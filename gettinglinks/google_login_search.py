import os
import time
import random
from dotenv import load_dotenv
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

load_dotenv()
GMAIL_ID = os.getenv("GMAIL_ID", "")
GMAIL_PASSWORD = os.getenv("GMAIL_PASSWORD", "")

_global_driver = None

def get_login_driver():
    global _global_driver
    if _global_driver is None:
        print("🌐 [Selenium] Starting visible browser for Google Login & Search...")
        options = uc.ChromeOptions()
        # Not using headless so we can bypass simple bot checks and see the login
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        # options.add_argument(f"--user-data-dir={os.path.join(os.getcwd(), 'chrome_profile')}") # Optional persistent profile
        try:
            _global_driver = uc.Chrome(options=options, version_main=149, use_subprocess=True)
            _global_driver.maximize_window()
        except Exception as e:
            print(f"❌ Login Selenium driver start error: {e}")
            _global_driver = None
    return _global_driver

def close_login_driver():
    global _global_driver
    if _global_driver is not None:
        print("🛑 Closing Selenium Browser...")
        try:
            _global_driver.quit()
        except Exception:
            pass
        _global_driver = None

def ensure_google_login(driver):
    """Check if logged in to Google. If not, try to login using .env credentials."""
    if not GMAIL_ID or not GMAIL_PASSWORD:
        print("  ⚠ GMAIL_ID or GMAIL_PASSWORD missing in .env. Skipping login.")
        return False
        
    try:
        driver.get("https://accounts.google.com/ServiceLogin")
        time.sleep(random.uniform(2, 4))
        
        # Check if already logged in by looking for email input
        email_inputs = driver.find_elements(By.XPATH, "//input[@type='email']")
        if not email_inputs:
            print("  ✅ Already logged in to Google.")
            return True
            
        print("  🔑 Logging in to Google...")
        email_input = email_inputs[0]
        for char in GMAIL_ID:
            email_input.send_keys(char)
            time.sleep(random.uniform(0.05, 0.15))
        email_input.send_keys(Keys.RETURN)
        time.sleep(random.uniform(3, 5))
        
        # Wait for password field
        password_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//input[@type='password']"))
        )
        for char in GMAIL_PASSWORD:
            password_input.send_keys(char)
            time.sleep(random.uniform(0.05, 0.15))
        password_input.send_keys(Keys.RETURN)
        
        # Wait to let login complete or captcha to appear
        time.sleep(random.uniform(5, 7))
        
        if "accounts.google.com/v3/signin" in driver.current_url:
            print("  ⚠ Login might require manual intervention (CAPTCHA / 2FA). Please solve it in the browser if possible. Waiting 20 seconds...")
            time.sleep(20)
            
        print("  ✅ Login sequence completed.")
        return True
    except Exception as e:
        print(f"  ❌ Google Login error: {e}")
        return False

def search_and_extract_gemini_and_links(query: str, num_results: int = 1) -> str:
    """Searches Google, extracts Gemini AI Overview (if any), and text from top links."""
    driver = get_login_driver()
    if not driver:
        return ""
        
    extracted_text = ""
    try:
        ensure_google_login(driver)
        
        driver.get("https://www.google.com")
        time.sleep(random.uniform(2, 4))
        
        # Search
        try:
            search_box = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.NAME, "q"))
            )
            search_box.clear()
            for char in query:
                search_box.send_keys(char)
                time.sleep(random.uniform(0.01, 0.05))
            time.sleep(0.5)
            search_box.send_keys(Keys.RETURN)
        except Exception as e:
            print(f"❌ Google search box error: {e}")
            return ""

        time.sleep(random.uniform(3, 6)) # Wait for Gemini to generate
        
        # Try to extract Gemini AI Overview
        try:
            print("  🤖 Looking for Gemini AI Overview...")
            # AI overviews are often in a block with specific structure, we'll try a broad text extraction of the top area
            # Sometimes it has class "kno-rdesc" or "hgKElc" or specific ARIA roles
            gemini_elements = driver.find_elements(By.CSS_SELECTOR, "div.s3v9rd, div.VwiC3b") # Broad overview snippets
            if gemini_elements:
                extracted_text += "--- Google Quick Info / Gemini Overview ---\n"
                # Combine top few snippets
                for el in gemini_elements[:3]:
                    if el.text.strip():
                        extracted_text += el.text + "\n"
                extracted_text += "-------------------------------------------\n\n"
        except Exception as e:
            print(f"  ⚠ Could not extract Gemini overview: {e}")

        # Extract top links
        try:
            elements = WebDriverWait(driver, 10).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, "a:has(h3)"))
            )
            links_list = []
            for elem in elements:
                link = elem.get_attribute("href")
                if link and "google.com" not in link and link not in links_list:
                    links_list.append(link)
        except Exception as e:
            print(f"❌ Google search results not found: {e}")
            return extracted_text

        print(f"📋 Found {len(links_list)} web links.")

        # Extract text from top N links
        for index, url in enumerate(links_list[:num_results], start=1):
            print(f"  [{index}/{num_results}] Opening: {url}")
            try:
                driver.get(url)
                time.sleep(random.uniform(2, 4))
                page_text = driver.execute_script("return document.body.innerText;")
                if page_text and len(page_text.strip()) > 100:
                    print(f"  ✅ Extracted {len(page_text)} chars from web.")
                    extracted_text += f"\n--- Source: {url} ---\n"
                    extracted_text += page_text[:5000] + "\n" # Limit to 5k chars per page
            except Exception as e:
                print(f"  ❌ Error opening link: {e}")

    except Exception as e:
        print(f"❌ General search extraction error: {e}")

    return extracted_text

if __name__ == "__main__":
    # Test
    res = search_and_extract_gemini_and_links("Nalanda University history", 1)
    print("\nResult Extracted:")
    print(res[:1000] + "...")
    close_login_driver()
