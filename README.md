# Daily Arxiv Newsletter

A self-hosted agentic service that emails you a curated daily digest of arXiv LLM papers, every morning.

---

## What it does

Each morning the service:

1. Queries arXiv for papers submitted in the last 48 hours (96 on Mondays)
2. Runs two targeted searches: one for **clinical LLM** papers, one for **general LLM** research
3. Asks an LLM to pick the 2 best clinical + 3 best general papers, reading abstracts only
4. Fetches the full text of each selected paper from arxiv.org
5. Asks an LLM to write a dense 350-word prose summary for each
6. Emails you the digest as plain text
7. Logs every paper seen to SQLite so nothing appears twice

The whole thing runs as a cron job. No server, no process, no uptime to manage.

## Stack

- Python 3, no frameworks
- [arXiv Python package](https://github.com/lukasschwab/arxiv.py) for fetching papers
- [OpenRouter](https://openrouter.ai) for LLM calls (primary: `x-ai/grok-4.1-fast`, fallback: `deepseek/deepseek-v3.2`)
- SQLite for deduplication
- [exe.dev](https://exe.dev) email gateway for sending mail (one POST request)
- Cron for scheduling

## Repository layout

```
newsletter.py    main orchestration and CLI entry point
fetcher.py       arXiv search queries and paper parsing
picker.py        LLM calls to select papers from abstracts
reader.py        full HTML text fetch from arxiv.org
summarizer.py    LLM calls to write summaries
emailver.py       plain-text email via gateway
db.py            SQLite seen-papers log
config.py        constants and environment loading
.env.example     template for secrets
```

## Setup

**Requirements:** Python 3.11+, an [OpenRouter](https://openrouter.ai) API key, an [exe.dev](https://exe.dev) VM for email delivery.

```bash
git clone https://github.com/yourname/daily-arxiv-newsletter
cd daily-arxiv-newsletter

pip install arxiv requests beautifulsoup4 python-dotenv

cp .env.example .env
# Edit .env and fill in your keys
```

## Configuration

`.env`:
```
OPENROUTER_API_KEY=sk-or-v1-...
MY_EMAIL=you@gmail.com        # must be your exe.dev account email
```

To change which models are used, edit `config.py`:
```python
PRIMARY_MODEL  = "x-ai/grok-4.1-fast"
FALLBACK_MODEL = "deepseek/deepseek-v3.2"
```

To change the search queries or paper counts, see `fetcher.py` (queries) and `picker.py` (limits).

## Running

```bash
# Test run — sends a real email, does not write to the production DB
python3 newsletter.py --test

# Production run
python3 newsletter.py
```

The script exits immediately if it already ran today (checked via log file), so it is safe to call from multiple cron entries.

## Scheduling

Two cron entries handle daylight saving time automatically:

```
0 5 * * * cd /path/to/daily-arxiv-newsletter && /usr/bin/python3 newsletter.py >> logs/cron.log 2>&1
0 6 * * * cd /path/to/daily-arxiv-newsletter && /usr/bin/python3 newsletter.py >> logs/cron.log 2>&1
```

Install with:
```bash
(crontab -l 2>/dev/null; echo "0 5 * * * cd /path/to/daily-arxiv-newsletter && /usr/bin/python3 newsletter.py >> logs/cron.log 2>&1") | crontab -
(crontab -l 2>/dev/null; echo "0 6 * * * cd /path/to/daily-arxiv-newsletter && /usr/bin/python3 newsletter.py >> logs/cron.log 2>&1") | crontab -
```

## Logs and database

```bash
# Follow today's run
tail -f logs/$(date +%Y-%m-%d).log

# See what was emailed
sqlite3 seen_papers.db \
  "SELECT run_date, track, title FROM seen_papers WHERE emailed=1 ORDER BY seen_at DESC LIMIT 20;"
```

## Note on email delivery

This project uses the [exe.dev](https://exe.dev) HTTP email gateway, which is specific to that platform. If you are running elsewhere, replace the `send()` function in `emailer.py` with any email provider you prefer (SMTP, Resend, Postmark, etc.). The function signature is straightforward.

## License

MIT
