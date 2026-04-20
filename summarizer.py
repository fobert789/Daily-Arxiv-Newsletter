import logging
from picker import call_llm


def summarize(paper: dict) -> dict:
    system_prompt = (
        "You are writing a daily research digest for an informatics PhD researcher "
        "specialising in large language models applied to healthcare and clinical medicine. "
        "The reader is highly technically literate and clinically informed. "
        "Write a thorough, specific, and engaging summary of the paper. "
        "Structure your response in flowing prose paragraphs (no bullet points, no headers) covering: "
        "1. What problem does this paper address and why does it matter? "
        "2. What approach or method did the authors use? Be specific — name architectures, "
        "datasets, model sizes, training procedures where mentioned. "
        "3. What are the key results and findings? Include concrete numbers where available. "
        "4. What limitations or open questions do the authors identify? "
        "End with a single sentence beginning exactly with 'Why this matters:' giving the "
        "key takeaway for someone working at the intersection of AI and medicine. "
        "Length: 320 to 380 words. Flowing prose only — no bullet points, no headers."
    )

    authors_str = ", ".join(paper["authors"][:5])
    if len(paper["authors"]) > 5:
        authors_str += ", et al."

    lines = [
        f"Title: {paper['title']}",
        f"Authors: {authors_str}",
        f"Categories: {', '.join(paper['categories'])}",
    ]
    if paper.get("journal_ref"):
        lines.append(f"Published in: {paper['journal_ref']}")
    if paper.get("comment"):
        lines.append(f"Authors note: {paper['comment']}")
    if paper.get("text_source") == "abstract_only":
        lines.append("Note: full text unavailable, summary based on abstract only.")
    lines.append("")
    lines.append("Full paper text:")
    lines.append(paper["full_text"])
    user_message = "\n".join(lines)

    try:
        summary, model_used = call_llm(system_prompt, user_message, max_tokens=1500)
        paper["summary"] = summary
        paper["model_used"] = model_used
        logging.info(f"Summary generated for {paper['arxiv_id']} by {model_used} ({len(summary)} chars)")
    except Exception as e:
        logging.error(f"Summary generation failed for {paper['arxiv_id']}: {e}")
        paper["summary"] = f"(Summary generation failed. Abstract: {paper['abstract']})"
        paper["model_used"] = "unknown"

    return paper


def summarize_all(papers: list) -> list:
    return [summarize(p) for p in papers]
