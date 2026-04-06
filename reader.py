import re
import logging
import requests
from bs4 import BeautifulSoup


def fetch_full_text(paper: dict) -> dict:
    arxiv_id = paper["arxiv_id"]
    url = f"https://arxiv.org/html/{arxiv_id}"
    try:
        r = requests.get(url, headers={"User-Agent": "arxiv-newsletter/1.0"}, timeout=20)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            for tag in soup.find_all(["nav", "header", "footer", "script",
                                      "style", "figure", "aside"]):
                tag.decompose()
            for tag in soup.find_all(class_=["ltx_bibliography", "ltx_appendix"]):
                tag.decompose()
            text = soup.get_text(separator="\n", strip=True)
            text = re.sub(r"\n{3,}", "\n\n", text)
            text = text[:12000]
            paper["full_text"] = text
            paper["text_source"] = "html"
            logging.info(f"HTML fetch succeeded for {arxiv_id} ({len(text)} chars)")
        else:
            raise ValueError(f"HTTP {r.status_code}")
    except Exception as e:
        logging.warning(f"HTML fetch failed for {arxiv_id}: {e} — using abstract")
        paper["full_text"] = paper["abstract"]
        paper["text_source"] = "abstract_only"
    return paper


def fetch_full_texts(papers: list) -> list:
    return [fetch_full_text(p) for p in papers]
