import json
import logging
import requests
import time

from config import OPENROUTER_API_KEY, MODELS

# How many candidates to carry forward from title screen into abstract screen
TITLE_SCREEN_KEEP = 15


def call_llm(system_prompt: str, user_message: str, max_tokens: int = 1000) -> str:
    """Call OpenRouter with native model fallback (no silent provider rerouting)."""
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    body = {
        "models": MODELS,
        "provider": {"allow_fallbacks": False},
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_message},
        ],
        "max_tokens": max_tokens,
    }
    r = requests.post(url, headers=headers, json=body, timeout=60)
    r.raise_for_status()
    data = r.json()
    content = data["choices"][0]["message"]["content"].strip()
    logging.info(f"LLM call succeeded with model: {data.get('model', 'unknown')}")
    return content


def _parse_json_ids(raw: str) -> list:
    """Extract a JSON array of IDs from LLM response, stripping markdown fences."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```")[1]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    ids = json.loads(cleaned.strip())
    if not isinstance(ids, list):
        raise ValueError(f"Expected list, got {type(ids)}")
    return [str(x) for x in ids]


def _ids_to_papers(ids: list, paper_map: dict) -> list:
    result = []
    for aid in ids:
        if aid in paper_map:
            result.append(paper_map[aid])
        else:
            logging.warning(f"LLM returned unknown arxiv_id: {aid}")
    return result


# ---------------------------------------------------------------------------
# Stage 1: title screen
# ---------------------------------------------------------------------------

def _title_screen(papers: list, system_prompt: str, label: str, keep: int) -> list:
    """
    Feed only titles + IDs to the LLM and ask it to shortlist `keep` candidates.
    Returns the shortlisted paper dicts.
    """
    if not papers:
        return []

    paper_map = {p["arxiv_id"]: p for p in papers}
    lines = [f"{p['arxiv_id']} | {p['title']}" for p in papers]
    title_block = "\n".join(lines)

    user_message = (
        f"Below are {len(papers)} {label} papers (ID | title).\n"
        f"Shortlist the {keep} most promising for a researcher specialising in "
        f"LLMs in healthcare. Use titles alone — no abstracts provided yet.\n"
        f"Return ONLY a JSON array of arxiv_ids. No explanation.\n\n"
        f"{title_block}"
    )

    raw = ""
    try:
        raw = call_llm(system_prompt, user_message, max_tokens=500)
        ids = _parse_json_ids(raw)
        shortlist = _ids_to_papers(ids[:keep], paper_map)
        logging.info(f"[{label}] Title screen: {len(papers)} → {len(shortlist)} candidates")
        return shortlist
    except Exception as e:
        logging.warning(f"[{label}] Title screen failed ({e}), raw: {raw!r} — passing all papers to abstract screen")
        return papers


# ---------------------------------------------------------------------------
# Stage 2: abstract screen
# ---------------------------------------------------------------------------

def _abstract_screen(papers: list, system_prompt: str, label: str, pick: int) -> list:
    """
    Feed full abstracts for the shortlisted candidates and pick the final `pick` papers.
    Returns the selected paper dicts.
    """
    if not papers:
        return []

    paper_map = {p["arxiv_id"]: p for p in papers}
    blocks = []
    for p in papers:
        lines = [
            f"ID: {p['arxiv_id']}",
            f"Title: {p['title']}",
            f"Authors: {', '.join(p['authors'][:3])}",
        ]
        if p.get("comment"):
            lines.append(f"Note: {p['comment']}")
        if p.get("journal_ref"):
            lines.append(f"Published in: {p['journal_ref']}")
        lines.append(f"Abstract: {p['abstract']}")
        lines.append("---")
        blocks.append("\n".join(lines))

    paper_text = "\n".join(blocks)
    user_message = (
        f"From these {len(papers)} {label} papers, pick the best {pick}.\n"
        f"Return ONLY a JSON array of arxiv_ids. No explanation.\n\n"
        f"{paper_text}"
    )

    raw = ""
    try:
        raw = call_llm(system_prompt, user_message, max_tokens=300)
        ids = _parse_json_ids(raw)
        selected = _ids_to_papers(ids[:pick], paper_map)
        logging.info(f"[{label}] Abstract screen: {len(papers)} → {len(selected)} final picks: {[p['arxiv_id'] for p in selected]}")
        return selected
    except Exception as e:
        logging.warning(f"[{label}] Abstract screen failed ({e}), raw: {raw!r} — falling back to first {pick} candidates")
        return papers[:pick]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def pick_papers(query_a: list, query_b: list) -> list:

    title_system = (
        "You are a research curator for an informatics PhD researcher specialising in "
        "large language models applied to healthcare and clinical medicine. "
        "Given a list of paper titles, shortlist the most promising candidates. "
        "Return ONLY a JSON array of arxiv_ids. No explanation, no markdown."
    )

    # ---- Clinical: 2-stage ----
    clinical_abstract_system = (
        "You are a research curator for an informatics PhD researcher specialising in "
        "applications of large language models in healthcare and clinical medicine. "
        "From the papers listed, identify the most interesting, novel, and impactful "
        "ones about LLMs in clinical or healthcare settings. "
        "Prioritise papers that: describe real deployment or evaluation of LLMs in "
        "clinical workflows, involve actual patient data or clinical tasks such as "
        "diagnosis, triage, documentation, drug recommendations, imaging interpretation, "
        "or genomics, represent meaningful methodological advances for healthcare AI, "
        "or are published in peer-reviewed journals. "
        "Return ONLY a JSON array of arxiv_ids. No explanation, no markdown, no "
        'preamble. Just the raw JSON array. Example: ["2504.01234", "2504.05678"]'
    )

    if not query_a:
        logging.info("No clinical papers found in this window.")
        clinical_picks = []
    else:
        clinical_candidates = _title_screen(query_a, title_system, "clinical", TITLE_SCREEN_KEEP)
        time.sleep(8)
        clinical_picks = _abstract_screen(clinical_candidates, clinical_abstract_system, "clinical", 2)

    logging.info(f"Clinical picks: {[p['arxiv_id'] for p in clinical_picks]}")

    # ---- General: 2-stage ----
    general_abstract_system = (
        "You are a research curator for an informatics PhD researcher specialising in "
        "large language models, with a focus on healthcare applications. "
        "From the papers listed, identify the most interesting, novel, and high-impact "
        "papers on LLMs. Prioritise: genuine architectural advances, important new "
        "benchmarks or evaluations, significant findings on reasoning, alignment, "
        "hallucination, retrieval-augmented generation, agentic systems, multimodal LLMs, "
        "fine-tuning methods, or in-context learning. Also consider strong work on LLM "
        "agents, tool use, chain-of-thought, and prompt engineering if it represents a "
        "real advance. Deprioritise narrow application papers unless exceptional. "
        "Return ONLY a JSON array of arxiv_ids. No explanation, no markdown, no "
        "preamble. Just the raw JSON array."
    )

    clinical_pick_ids = {p["arxiv_id"] for p in clinical_picks}
    query_b_filtered = [p for p in query_b if p["arxiv_id"] not in clinical_pick_ids]

    if not query_b_filtered:
        logging.info("No general papers to evaluate after filtering.")
        general_picks = []
    else:
        general_candidates = _title_screen(query_b_filtered, title_system, "general", TITLE_SCREEN_KEEP)
        time.sleep(8)
        general_picks = _abstract_screen(general_candidates, general_abstract_system, "general", 3)

    logging.info(f"General picks: {[p['arxiv_id'] for p in general_picks]}")

    # ---- Final selection ----
    combined = clinical_picks + general_picks

    # Fill clinical slots from general if needed
    if len(clinical_picks) < 2:
        shortfall = 2 - len(clinical_picks)
        combined_ids = {p["arxiv_id"] for p in combined}
        extras = [p for p in general_picks if p["arxiv_id"] not in combined_ids]
        combined = clinical_picks + general_picks + extras[:shortfall]

    combined = combined[:5]
    logging.info(f"Final selection ({len(combined)} papers): {[p['arxiv_id'] for p in combined]}")
    return combined
