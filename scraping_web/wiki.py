import requests
import time
from fake_useragent import UserAgent

url = "https://tourism.bihar.gov.in/hi/destinations/kaimur/mundeshwari-devi-temple"

# r = requests.get("https://kaimur.nic.in/hi/tourist-place/%E0%A4%9A%E0%A4%BF%E0%A4%B2%E0%A4%BF%E0%A4%95%E0%A4%BE-%E0%A4%AC%E0%A4%B0%E0%A4%95%E0%A5%81%E0%A4%B2/")

session = requests.Session()

headers = {
    "User-Agent": UserAgent().random,
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    'Referer' : 'https://www.google.com/'
}

# proxy = {
#     "http": 
#     "https":

time.sleep(2)  # Sleep for 2 seconds to mimic human behavior



r = session.get(url, headers=headers)

print(r.text)
with open("file.html", "w", encoding='utf-8') as f:
    f.write(r.text)
    
    