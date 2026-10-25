"""
selenium_search.py — Background (headless) web search and extraction using undetected_chromedriver.
"""
from gettinglinks.chrome_config import find_chrome, chrome_major_version


import time
import random
import undetected_chromedriver as uc
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


_global_driver = None

def get_driver():
    global _global_driver
    if _global_driver is None:
        import os
        options = uc.ChromeOptions()
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        
        # Temporary/Guest profile settings
        print("🌐 [Selenium] Headless browser start ho raha hai (Guest/Temporary profile ke sath)...")
        try:
            _global_driver = uc.Chrome(
                options=options, 
                browser_executable_path=find_chrome(),
                version_main=chrome_major_version(),
                use_subprocess=True
            )
        except Exception as e:
            print(f"❌ Selenium driver start error: {e}")
            _global_driver = None
    return _global_driver

def close_browser():
    global _global_driver
    if _global_driver is not None:
        print("🛑 Closing Selenium Browser...")
        try:
            _global_driver.quit()
        except Exception:
            pass
        _global_driver = None

def search_and_extract_text(query: str, num_results: int = 2) -> list:
    """
    Google search karta hai, top links open karta hai aur innerText nikalta hai.
    """
    driver = get_driver()
    if not driver:
        return []

    extracted_data = []

    try:
        driver.get("https://www.google.com")
        time.sleep(random.uniform(1.5, 3))
        
        # Search box dhundo aur type karo
        try:
            search_box = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.NAME, "q"))
            )
            for char in query:
                search_box.send_keys(char)
                time.sleep(random.uniform(0.01, 0.05))
            time.sleep(0.5)
            search_box.send_keys(Keys.RETURN)
        except Exception as e:
            print(f"❌ Google search box nahi mila: {e}")
            return extracted_data

        time.sleep(random.uniform(2, 4))
        
        # Links extract karo
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
            print(f"❌ Google search results nahi mile: {e}")
            return extracted_data

        print(f"📋 Total {len(links_list)} links mile Google se.")

        # Links open karo aur text nikal lo (headless safe)
        for index, url in enumerate(links_list[:num_results], start=1):
            print(f"\n  [{index}/{num_results}] Opening link: {url}")
            try:
                driver.get(url)
                time.sleep(random.uniform(2, 4))
                
                # JavaScript ke through text extract karo (Ctrl+C ka best alternative)
                page_text = driver.execute_script("return document.body.innerText;")
                
                if page_text and len(page_text.strip()) > 100:
                    print(f"  ✅ Text extracted: {len(page_text)} characters.")
                    # Hum list of [text, images, url] return karte hain
                    extracted_data.append([page_text, [], url])
                else:
                    print("  ⚠ Page par sufficient text nahi mila.")
            except Exception as loop_error:
                print(f"  ❌ Link open/extract me error: {loop_error}")

    except Exception as e:
        print(f"❌ Selenium search process me error: {e}")

    return extracted_data
