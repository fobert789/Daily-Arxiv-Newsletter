import sqlite3, logging
from datetime import datetime, timezone

DB_PATH = "/home/ubuntu/newsletter/seen_papers.db"

def get_conn(db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS seen_papers (
            arxiv_id      TEXT PRIMARY KEY,
            version       INTEGER,
            title         TEXT,
            track         TEXT,
            seen_at       TEXT,
            emailed       INTEGER DEFAULT 0,
            run_date      TEXT
        )
    """)
    conn.commit()
    return conn

def get_seen_ids(db_path=DB_PATH) -> set:
    conn = get_conn(db_path)
    rows = conn.execute("SELECT arxiv_id FROM seen_papers").fetchall()
    conn.close()
    return {r[0] for r in rows}

def log_papers(all_papers: list, emailed_ids: list, db_path=DB_PATH):
    conn = get_conn(db_path)
    now = datetime.now(timezone.utc).isoformat()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for p in all_papers:
        conn.execute(
            "INSERT OR IGNORE INTO seen_papers "
            "(arxiv_id, version, title, track, seen_at, emailed, run_date) "
            "VALUES (?, ?, ?, ?, ?, 0, ?)",
            (p["arxiv_id"], p["version"], p["title"], p["track"], now, today)
        )
    for aid in emailed_ids:
        conn.execute(
            "UPDATE seen_papers SET emailed=1 WHERE arxiv_id=?", (aid,)
        )
    conn.commit()
    conn.close()
    logging.info(f"DB updated: {len(all_papers)} total papers logged, "
                 f"{len(emailed_ids)} marked as emailed.")
