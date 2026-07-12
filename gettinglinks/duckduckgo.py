from html.parser import HTMLParser
from urllib.parse import parse_qs, urlencode, unquote, urlparse
from urllib.request import Request, urlopen


class DuckDuckGoParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return

        attrs = dict(attrs)
        class_name = attrs.get("class", "")
        href = attrs.get("href", "")

        if "result__a" not in class_name or not href:
            return

        self.links.append(clean_duckduckgo_link(href))


def clean_duckduckgo_link(link):
    parsed_link = urlparse(link)
    query_data = parse_qs(parsed_link.query)

    if "uddg" in query_data:
        return unquote(query_data["uddg"][0])

    if link.startswith("//"):
        return "https:" + link

    return link


def get_duckduckgo_links(query, limit=3):
    params = {
        "q": query,
        "kl": "in-en",
    }
    url = "https://html.duckduckgo.com/html/?" + urlencode(params)

    try:
        request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(request, timeout=20) as response:
            html = response.read().decode("utf-8", errors="ignore")
    except Exception as error:
        print(f"DuckDuckGo error: {error}")
        return []

    parser = DuckDuckGoParser()
    parser.feed(html)

    return parser.links[:limit]
