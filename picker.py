import json
import logging
import requests
import time

from config import OPENROUTER_API_KEY, PRIMARY_MODEL, FALLBACK_MODEL, PICKER_BATCH_SIZE


def call_llm(system_prompt: str, user_message: str, max_tokens: int = 1000) -> str:
    """Call OpenRouter. Try PRIMARY_MODEL, fall back to FALLBACK_MODEL on error."""
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    for model in [PRIMARY_MODEL, FALLBACK_MODEL]:
        try:
            body = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_message},
                ],
                "max_tokens": max_tokens,
            }
            r = requests.post(url, headers=headers, json=body, timeout=60)
            r.raise_for_status()
            content = r.json()["choices"][0]["message"]["content"].strip()
            logging.info(f"LLM call succeeded with model: {model}")
            return content
        except Exception as e:
            logging.warning(f"LLM call failed with {model}: {e}")
    raise RuntimeError("Both PRIMARY_MODEL and FALLBACK_MODEL failed.")


def _paper_block(p: dict) -> str:
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
    return "\n".join(lines)


def _pick_from_list(papers: list, system_prompt: str, label: str) -> list:
    """Run batched LLM calls and return all selected arxiv_ids."""
    if not papers:
        return []

    batches = [papers[i:i + PICKER_BATCH_SIZE] for i in range(0, len(papers), PICKER_BATCH_SIZE)]
    total = len(batches)
    all_ids = []

    for i, batch in enumerate(batches, start=1):
        prefix = f"(Batch {i} of {total}) " if total > 1 else ""
        paper_text = "\n".join(_paper_block(p) for p in batch)
        user_message = (
            f"{prefix}Evaluate these {label} papers and return the best arxiv_ids "
            f"as a JSON array.\n\n{paper_text}"
        )
        raw = ""
        try:
            raw = call_llm(system_prompt, user_message)
            # Strip markdown fences if present
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("```")[1]
                if cleaned.startswith("json"):
                    cleaned = cleaned[4:]
            ids = json.loads(cleaned.strip())
            if isinstance(ids, list):
                all_ids.extend(str(x) for x in ids)
                logging.info(f"[{label}] Batch {i}/{total}: got {len(ids)} ids")
            else:
                logging.warning(f"[{label}] Batch {i}/{total}: unexpected type {type(ids)}")
        except Exception as e:
            logging.warning(f"[{label}] Batch {i}/{total}: parse/call failed — {e}. Raw: {raw!r}")
        time.sleep(8)

    # Deduplicate preserving order
    seen = set()
    deduped = []
    for x in all_ids:
        if x not in seen:
            seen.add(x)
            deduped.append(x)
    return deduped


def _ids_to_papers(ids: list, paper_map: dict) -> list:
    result = []
    for aid in ids:
        if aid in paper_map:
            result.append(paper_map[aid])
        else:
            logging.warning(f"LLM returned unknown arxiv_id: {aid}")
    return result


def pick_papers(query_a: list, query_b: list) -> list:
    # ---- Clinical picks ----
    clinical_system = (
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
        'preamble. Just the raw JSON array. Example: [\"2504.01234\", \"2504.05678\"]'
    )

    if not query_a:
        logging.info("No clinical papers found in this window.")
        clinical_ids = []
    else:
        clinical_ids = _pick_from_list(query_a, clinical_system, "clinical")

    map_a = {p["arxiv_id"]: p for p in query_a}
    clinical_picks = _ids_to_papers(clinical_ids[:min(2, len(clinical_ids))], map_a)
    logging.info(f"Clinical picks: {[p['arxiv_id'] for p in clinical_picks]}")

    # ---- General picks ----
    general_system = (
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

    # Remove clinical picks from query_b
    clinical_pick_ids = {p["arxiv_id"] for p in clinical_picks}
    query_b_filtered = [p for p in query_b if p["arxiv_id"] not in clinical_pick_ids]

    if not query_b_filtered:
        logging.info("No general papers to evaluate after filtering.")
        general_ids = []
    else:
        general_ids = _pick_from_list(query_b_filtered, general_system, "general")

    map_b = {p["arxiv_id"]: p for p in query_b_filtered}
    general_picks = _ids_to_papers(general_ids[:min(3, len(general_ids))], map_b)
    logging.info(f"General picks: {[p['arxiv_id'] for p in general_picks]}")

    # ---- Final selection ----
    combined = clinical_picks + general_picks

    # Fill clinical slots from general if needed
    if len(clinical_picks) < 2:
        shortfall = 2 - len(clinical_picks)
        # Pull extras from general that aren't already in combined
        combined_ids = {p["arxiv_id"] for p in combined}
        extras = [p for p in general_picks if p["arxiv_id"] not in combined_ids]
        combined = clinical_picks + general_picks + extras[:shortfall]

    combined = combined[:5]
    logging.info(f"Final selection ({len(combined)} papers): {[p['arxiv_id'] for p in combined]}")
    return combined
