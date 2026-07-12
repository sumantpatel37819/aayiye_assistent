"""
browser_search.py — Playwright se real browser open karo, DuckDuckGo pe jaao,
query search karo aur top search result links lo.

No API key needed — DuckDuckGo pe CAPTCHA nahi aate.
"""

import asyncio
from playwright.async_api import async_playwright
import urllib.parse


# async def google_search_links(query: str, num_results: int = 4) -> list:
#     """
#     Real browser se DuckDuckGo search karo aur top links return karo.
#     (Function name wahi rakha gaya hai taaki imports break na ho)

#     Args:
#         query       : search query string
#         num_results : kitne links chahiye (default 4)

#     Returns:
#         list of URLs
#     """
#     links = []

#     async with async_playwright() as p:
#         browser = await p.chromium.launch(
#             headless=False,          # Browser dikhega
#             args=["--start-maximized"]
#         )
#         context = await browser.new_context(
#             viewport={"width": 1280, "height": 800},
#             user_agent=(
#                 "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
#                 "AppleWebKit/537.36 (KHTML, like Gecko) "
#                 "Chrome/124.0.0.0 Safari/537.36"
#             ),
#             locale="en-IN"
#         )
#         page = await context.new_page()

#         print(f"🌐 Browser khul raha hai — DuckDuckGo pe ja raha hoon...")
        
#         # Seedha DuckDuckGo search URL pe jaao (JS rendered page)
#         encoded_query = urllib.parse.quote_plus(query)
#         search_url = f"https://duckduckgo.com/?q={encoded_query}&t=h_&ia=web"
        
#         try:
#             await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
#             print(f"🔍 Search ho rahi hai: '{query}'")
            
#             # Results load hone ka wait karo
#             # DuckDuckGo ke results "li[data-layout='organic']" ya "[data-testid='result']" hote hain
#             await page.wait_for_selector('[data-testid="result-title-a"], a.result__url', timeout=15000)
            
#             # Search result links extract karo
#             result_anchors = await page.locator('[data-testid="result-title-a"], a.result__url').all()

#             for anchor in result_anchors:
#                 try:
#                     href = await anchor.get_attribute("href")
#                     if href and href.startswith("http") and "duckduckgo.com" not in href:
#                         if href not in links:
#                             links.append(href)
#                             print(f"  ✅ Link mila: {href}")
#                     if len(links) >= num_results:
#                         break
#                 except Exception:
#                     continue
#         except Exception as e:
#             print(f"❌ DuckDuckGo search error: {e}")

#         print(f"\n📋 Total {len(links)} links mile DuckDuckGo se.")
#         await browser.close()

#     return links

# from selenium import webdriver
import undetected_chromedriver as webdriver
import time
import random
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import os
import tkinter as tk
from selenium.webdriver.common.action_chains import ActionChains


options = webdriver.ChromeOptions()
# options.add_argument(r"--user-data-dir=C:/Users/hacke/AppData/Local/Google/Chrome/User Data")  # Apne Chrome user data path se replace karo
# options.add_argument("--profile-directory=Default")  # Apne Chrome profile directory se replace karo

driver = webdriver.Chrome(options=options, use_subprocess=True)

try:
    driver.get("https://www.google.com")
    
    time.sleep(random.uniform(2, 4))  # Random delay to mimic human behavior
    
    
    search_box = driver.find_element(By.NAME, "q")
    
    search_text = "Mahavir mandir patna english me"
    
    for char in search_text:
        search_box.send_keys(char)
        time.sleep(random.uniform(0.01, 0.03))  # Random delay between keystrokes
    
    time.sleep(1)
    search_box.send_keys(Keys.RETURN)
    time.sleep(5)
    print("Page title:", driver.title)
    # time.sleep(5)
    try:
        elements = WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "a:has(h3)"))
        )
        links_list = []
        for elem in elements:
            link = elem.get_attribute("href")
            if link and "google.com" not in link and "github.com" not in link and link not in links_list:
                links_list.append(link)
                print("Found link:", link)
        print("Total links found:", len(links_list))
        
        for index, url in enumerate(links_list[:1], start=1):
            print(f"Opening link {index}: {url}")
            driver.get(url)
            time.sleep(random.uniform(2, 4))  # Random delay to mimic human behavior
            # page_text = driver.find_element(By.TAG_NAME, "body").text
            # print("page data preview:\n", "\n".join(page_text.splitlines()[:10]))  # Page text ka preview (first 10 lines
            # time.sleep(random.uniform(1,2))
            # print("getting data by get elements", page_text[:1000])
            print("*"*50)
            try:
                driver.execute_cdp_cmd("Page.reload", {"ignoreCache": False, "scriptToEvaluateOnLoad": "chrome.transalate.translate('en)"})
                time.sleep(random.uniform(2, 4))  # Random delay to mimic human behavior
                print("Page successfully reloaded with translation script.")
            except Exception as translation_error:
                print("Error during page reload with translation script:", translation_error)
            
            
            
            body_element = driver.find_element(By.TAG_NAME, "body")
            body_element.click()
            time.sleep(0.3)
            
            body_element.send_keys(Keys.CONTROL + 'a')  # Select all text
            time.sleep(0.3)
            body_element.send_keys(Keys.CONTROL + 'c')  # Copy selected text
            time.sleep(0.3)
            root = tk.Tk()
            root.withdraw()
            copied_text = root.clipboard_get()
            root.destroy()
            print("Successfully copied page text to clipboard.", len(copied_text))
            # print("Copied text preview:\n", "\n".join(copied_text.splitlines()))
            
            print("*"*50)
            
            # body_element.click()
            
            # images = driver.find_elements(By.TAG_NAME, "img")
            # valid_img = None
            # for img in images:
            #     if img.is_displayed() and img.size['width'] > 50:
            #         valid_img = img
            #         break
            # if valid_img:
            #     print("Valid image found, clicking to open in new tab.")
            #     actions = ActionChains(driver)
            #     actions.move_to_element(valid_img).context_click().perform()
            #     time.sleep(0.5)
                
            #     actions.send_keys('o').perform()
            #     time.sleep(2)

            #     root = tk.Tk()
            #     root.withdraw()
            #     copied_img_url = root.clipboard_get()
            #     root.destroy()
            #     print("Copied image URL:", copied_img_url)
            # else:
            #     print("No valid image found to open.")
            #   # Copied text ka preview (first 10 lines)

            # time.sleep(random.uniform(1, 2))
    
    except Exception as loop_error:
        print("Error during link extraction or navigation:", loop_error)
        
except Exception as e:
    print("Error:", e)
finally:
    try:
        driver.close()
    except Exception:
        pass
    
