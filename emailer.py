import requests
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from config import MY_EMAIL

GATEWAY_URL = "http://169.254.169.254/gateway/email/send"


def _divider(char="─", width=60):
    return char * width


def _format_body(selected: list, stats: dict) -> str:
    oslo = ZoneInfo("Europe/Oslo")
    date_oslo = datetime.now(oslo).strftime("%A %-d %B %Y")
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    len_a = stats.get("len_a", 0)
    len_b = stats.get("len_b", 0)

    lines = []
    lines.append("arXiv Research Digest")
    lines.append(date_oslo)
    lines.append(f"Scanned: {len_a} clinical · {len_b} general · {len(selected)} selected")
    lines.append(_divider("="))
    lines.append("")

    for i, p in enumerate(selected, 1):
        track_label = "[CLINICAL LLM]" if p["track"] == "clinical" else "[GENERAL LLM]"
        authors_str = ", ".join(p["authors"][:4])
        if len(p["authors"]) > 4:
            authors_str += " et al."

        lines.append(f"{i}. {track_label}  {p.get('primary_category', '')}")
        lines.append(p["title"])
        lines.append(f"Authors: {authors_str}")
        if p.get("journal_ref"):
            lines.append(f"Published in: {p['journal_ref']}")
        lines.append(f"https://arxiv.org/abs/{p['arxiv_id']}")
        lines.append("")
        lines.append(p.get("summary", ""))
        lines.append("")
        lines.append(_divider())
        lines.append("")

    lines.append(f"Generated {timestamp} · Europe/Oslo timezone")
    return "\n".join(lines)


def send(selected: list, stats: dict, test_mode: bool = False, test_path: str = "test_email.html"):
    oslo = ZoneInfo("Europe/Oslo")
    date_oslo = datetime.now(oslo).strftime("%A %-d %B %Y")

    n_clinical = sum(1 for p in selected if p["track"] == "clinical")
    n_general  = sum(1 for p in selected if p["track"] == "general")

    if not selected:
        subject = f"arXiv Digest — {date_oslo} — Quiet day"
        body = (
            f"arXiv Research Digest — {date_oslo}\n\n"
            f"No new papers were found matching your criteria in the current "
            f"lookback window ({stats.get('lookback_hours', '?')} hours).\n"
            f"This is normal on weekends or quiet days.\n"
        )
    else:
        subject = f"arXiv Digest — {date_oslo} — {n_clinical} clinical · {n_general} general"
        body = _format_body(selected, stats)

    if test_mode:
        with open(test_path, "w") as f:
            f.write(body)
        logging.info(f"Test mode: email text written to {test_path}")
        return

    payload = {"to": MY_EMAIL, "subject": subject, "body": body}
    try:
        r = requests.post(GATEWAY_URL, json=payload, timeout=15)
        r.raise_for_status()
        resp = r.json()
        if resp.get("success"):
            logging.info(f"Email sent successfully to {MY_EMAIL}")
        else:
            logging.error(f"Email gateway returned error: {resp}")
    except Exception as e:
        logging.error(f"Failed to send email: {e}")
        raise


def send_failure(error_text: str, test_mode: bool = False):
    oslo = ZoneInfo("Europe/Oslo")
    date_oslo = datetime.now(oslo).strftime("%Y-%m-%d")
    subject = f"arXiv Digest FAILED — {date_oslo}"
    payload = {"to": MY_EMAIL, "subject": subject, "body": error_text}
    if test_mode:
        logging.error(f"Test mode failure notice: {error_text[:200]}")
        return
    try:
        requests.post(GATEWAY_URL, json=payload, timeout=15)
    except Exception:
        pass
