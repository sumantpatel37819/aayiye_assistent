import trafilatura
from pathlib import Path


RAW_HTML_DIR = Path(__file__).parent / "raw_html"


def extract_html_file(html_file):
    with open(html_file, "r", encoding="utf-8") as f:
        html_content = f.read()

    cleaned_text = trafilatura.extract(
        html_content,
        include_links=False,
        include_images=True,
        output_format="txt"
    )

    print(f"\n================ {html_file.name} ================")

    if cleaned_text:
        return cleaned_text
    
    return "Is file se text extract nahi kar paaya."


def main():
    if not RAW_HTML_DIR.exists():
        print("raw_html folder nahi mila.")
        return

    html_files = list(RAW_HTML_DIR.glob("*.html"))

    if not html_files:
        print("raw_html folder me koi html file nahi hai.")
        return

    for html_file in html_files:
        extract_html_file(html_file)


if __name__ == "__main__":
    main()
    
    
    
# import trafilatura
# from pathlib import Path

# RAW_HTML_DIR = Path(__file__).parent / "raw_html"

# with open(RAW_HTML_DIR / "file.html", "r", encoding='utf-8') as f:
#     html_content = f.read()

# cleaned_text = trafilatura.extract(
#     html_content,
#     include_links=False,
#     include_images=True,
#     output_format='txt'
#     )

# print(cleaned_text)