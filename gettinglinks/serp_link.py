import json
import os
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def load_serp_api_key():
    env_path = Path(__file__).resolve().parent.parent / ".env"

    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("SERP_API_KEY="):
                return line.split("=", 1)[1].strip()

    return os.getenv("SERP_API_KEY")


def get_serp_links(query, limit=3):
    api_key = load_serp_api_key()

    if not api_key:
        print("SERP_API_KEY .env file me nahi mila.")
        return []

    params = {
        "engine": "google",
        "q": query,
        "api_key": api_key,
        "num": limit,
        "google_domain": "google.co.in",
        "gl": "in",
        "hl": "en",
        "location": "India",
    }
    url = "https://serpapi.com/search.json?" + urlencode(params)

    try:
        request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(request, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception as error:
        print(f"SerpAPI error: {error}")
        return []

    links = []
    for result in data.get("organic_results", []):
        link = result.get("link")
        if link:
            links.append(link)

    return links[:limit]
