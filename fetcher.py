import arxiv
import logging
import time
from datetime import datetime, timezone, timedelta

from config import ARXIV_PAGE_SIZE, ARXIV_DELAY


def _lookback_hours() -> int:
    now = datetime.now(timezone.utc)
    return 96 if now.weekday() == 0 else 48


def _date_filter(hours: int) -> str:
    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=hours)
    fmt = "%Y%m%d%H%M%S"
    return f"[{start.strftime(fmt)} TO {now.strftime(fmt)}]"


def _build_paper(result, track: str) -> dict:
    entry_id = result.entry_id  # e.g. https://arxiv.org/abs/2504.01234v2
    parts = entry_id.split("/")[-1]  # "2504.01234v2"
    if "v" in parts:
        arxiv_id, ver_str = parts.rsplit("v", 1)
        try:
            version = int(ver_str)
        except ValueError:
            version = 1
    else:
        arxiv_id = parts
        version = 1

    return {
        "arxiv_id":        arxiv_id,
        "version":         version,
        "title":           result.title,
        "abstract":        result.summary.replace("\n", " "),
        "authors":         [a.name for a in result.authors],
        "categories":      result.categories,
        "primary_category": result.primary_category,
        "published":       result.published.isoformat(),
        "comment":         result.comment or "",
        "journal_ref":     result.journal_ref or "",
        "pdf_url":         result.pdf_url,
        "html_url":        f"https://arxiv.org/html/{arxiv_id}",
        "track":           track,
    }


def _fetch_query(query: str, date_filter: str, track: str, seen_ids: set) -> list:
    client = arxiv.Client(page_size=ARXIV_PAGE_SIZE, delay_seconds=ARXIV_DELAY, num_retries=3)
    search = arxiv.Search(
        query=f"{query} AND submittedDate:{date_filter}",
        max_results=100,
        sort_by=arxiv.SortCriterion.SubmittedDate,
        sort_order=arxiv.SortOrder.Descending,
    )

    results = []
    seen_in_batch = set()
    for r in client.results(search):
        paper = _build_paper(r, track)
        if paper["arxiv_id"] in seen_in_batch:
            continue
        seen_in_batch.add(paper["arxiv_id"])
        results.append(paper)

    logging.info(f"[{track}] Fetched {len(results)} papers from arXiv")

    filtered = [p for p in results if p["arxiv_id"] not in seen_ids]
    already_seen_count = len(results) - len(filtered)
    logging.info(f"[{track}] {already_seen_count} filtered as already-seen, {len(filtered)} remain")

    return filtered


def fetch_papers(seen_ids: set) -> tuple:
    hours = _lookback_hours()
    date_filter = _date_filter(hours)
    logging.info(f"Lookback window: {hours} hours. Date filter: {date_filter}")

    logging.info("Sleeping 10s before arXiv API calls (cold-start protection)...")
    time.sleep(10)

    query_a = (
        '(ti:"large language model" OR ti:"large language models" OR '
        'ti:LLM OR ti:LLMs OR ti:GPT OR ti:ChatGPT OR ti:"foundation model" OR '
        'ti:"generative AI" OR ti:"artificial intelligence") AND ('
        'ti:clinical OR ti:medical OR ti:medicine OR ti:hospital OR '
        'ti:patient OR ti:patients OR ti:diagnosis OR ti:diagnostic OR '
        'ti:EHR OR ti:"electronic health record" OR ti:radiology OR '
        'ti:pathology OR ti:physician OR ti:clinician OR ti:healthcare OR '
        'ti:health OR ti:drug OR ti:therapy OR ti:treatment OR ti:imaging OR '
        'ti:genomic OR ti:biomedical OR ti:nursing OR ti:pharmacy OR '
        'ti:oncology OR ti:surgery)'
    )

    query_b = (
        '(cat:cs.CL OR cat:cs.AI OR cat:cs.LG) AND ('
        'ti:"large language model" OR ti:"large language models" OR '
        'ti:LLM OR ti:LLMs OR '
        'ti:"language model" OR ti:"language models" OR '
        'ti:RAG OR ti:"retrieval augmented generation" OR ti:"retrieval-augmented" OR '
        'ti:agent OR ti:agents OR ti:agentic OR '
        'ti:"tool use" OR ti:"tool calling" OR '
        'ti:"long context" OR ti:"context window" OR '
        'ti:memory OR ti:"external memory" OR '
        'ti:"chain of thought" OR ti:"chain-of-thought" OR '
        'ti:"prompt" OR ti:"prompting" OR ti:"in-context learning" OR '
        'ti:alignment OR ti:RLHF OR ti:"reinforcement learning from human feedback" OR '
        'ti:"instruction tuning" OR ti:"instruction following" OR '
        'ti:"fine-tuning" OR ti:"finetuning" OR '
        'ti:hallucination OR '
        'ti:"multi-agent" OR ti:"multi agent")'
    )

    papers_a = _fetch_query(query_a, date_filter, "clinical", seen_ids)
    papers_b = _fetch_query(query_b, date_filter, "general", seen_ids)

    return papers_a, papers_b
