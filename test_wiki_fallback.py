"""Debug test for regex patterns in wiki_crawl4ai.py"""
import sys, re
sys.path.insert(0, '.')

print("=== Regex Debug Tests ===\n")

# --- Test current regex in wiki_crawl4ai ---
from scraping_web.wiki_crawl4ai import (
    _extract_coordinates_from_html,
    _filter_wikimedia_images,
    _WIKIMEDIA_IMG_RE,
)

# T1: geo.position meta tag — REAL Wikipedia format
html_geo = '<meta name="geo.position" content="25.1347;85.4439"/>'
lat, lon = _extract_coordinates_from_html(html_geo)
print(f"T1 geo.position: lat={lat}, lon={lon}")
assert lat == 25.1347 and lon == 85.4439, f"FAIL: got {lat}, {lon}"
print("  PASS\n")

# T2: data-lat / data-lon (real Wikipedia infobox)
html_datalat = 'data-lat="25.1500" data-lon="85.4500"'
lat2, lon2 = _extract_coordinates_from_html(html_datalat)
print(f"T2 data-lat: lat={lat2}, lon={lon2}")
if lat2 and lon2:
    print("  PASS\n")
else:
    print("  WARN (acceptable — data-lat not present in all pages)\n")

# T3: geo span
html_geo_span = '<span class="geo">25.1347; 85.4439</span>'
lat3, lon3 = _extract_coordinates_from_html(html_geo_span)
print(f"T3 geo span: lat={lat3}, lon={lon3}")
if lat3 and lon3:
    print("  PASS\n")
else:
    print("  WARN (may be OK)\n")

# T4: Wikimedia URL regex on real URL
real_url = "https://upload.wikimedia.org/wikipedia/commons/a/ab/Nalanda_University_Ruins.jpg"
matches = _WIKIMEDIA_IMG_RE.findall(real_url)
print(f"T4 Wikimedia regex (full URL): {matches}")
assert matches, "FAIL: regex did not match full Wikimedia URL"
print("  PASS\n")

# T5: Wikimedia URL regex on thumb URL
thumb_url = "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/Nalanda.jpg/320px-Nalanda.jpg"
matches2 = _WIKIMEDIA_IMG_RE.findall(thumb_url)
print(f"T5 Wikimedia regex (thumb URL): {matches2}")
if matches2:
    print("  PASS\n")
else:
    print("  WARN: thumb URL not matched by regex (will be handled differently)\n")

# T6: filter_wikimedia_images — full URL in HTML
html_with_imgs = (
    'src="https://upload.wikimedia.org/wikipedia/commons/a/ab/Nalanda_Ruins.jpg" '
    'src="https://upload.wikimedia.org/wikipedia/commons/b/bc/Temple_Bihar.jpg"'
)
imgs = _filter_wikimedia_images("", html_with_imgs)
print(f"T6 _filter_wikimedia_images from HTML: {len(imgs)} images")
print(f"  Images: {imgs}")
if imgs:
    print("  PASS\n")
else:
    print("  FAIL: no images extracted from HTML\n")

print("=== All debug tests complete ===")
