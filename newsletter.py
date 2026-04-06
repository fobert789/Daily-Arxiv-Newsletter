#!/usr/bin/env python3
import argparse
import logging
import os
import sys
import traceback
from datetime import datetime
from zoneinfo import ZoneInfo


def already_ran_today():
    oslo = ZoneInfo("Europe/Oslo")
    today = datetime.now(oslo).strftime("%Y-%m-%d")
    log_file = f"/home/ubuntu/newsletter/logs/{today}.log"
    return os.path.exists(log_file)


def setup_logging(test_mode: bool):
    oslo = ZoneInfo("Europe/Oslo")
    today = datetime.now(oslo).strftime("%Y-%m-%d")
    os.makedirs("/home/ubuntu/newsletter/logs", exist_ok=True)
    log_file = f"/home/ubuntu/newsletter/logs/{today}.log"
    handlers = [logging.StreamHandler(sys.stdout)]
    if not test_mode:
        handlers.append(logging.FileHandler(log_file))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=handlers,
    )
    return log_file


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true",
                        help="Run full pipeline but write email to test_email.html, use test_seen.db")
    args = parser.parse_args()

    # DST guard: exit immediately if already ran today (only in non-test mode)
    if not args.test and already_ran_today():
        print("Already ran today, exiting.")
        sys.exit(0)

    log_file = setup_logging(args.test)
    logging.info("=== arXiv newsletter run starting ===")
    if args.test:
        logging.info("Running in TEST MODE — email will be sent, DB will NOT be updated")

    db_path = ("/home/ubuntu/newsletter/test_seen.db"
               if args.test else "/home/ubuntu/newsletter/seen_papers.db")

    try:
        from dotenv import load_dotenv
        load_dotenv("/home/ubuntu/newsletter/.env")

        import db
        import fetcher
        import picker
        import reader
        import summarizer
        import emailer

        # 1. Get already-seen IDs
        seen_ids = db.get_seen_ids(db_path)
        logging.info(f"Loaded {len(seen_ids)} already-seen paper IDs from DB")

        # 2. Fetch papers
        query_a, query_b = fetcher.fetch_papers(seen_ids)
        logging.info(f"Fetched: {len(query_a)} clinical, {len(query_b)} general")

        # 3. Handle empty case
        if not query_a and not query_b:
            logging.info("No papers found. Sending quiet-day notice.")
            from datetime import datetime as dt, timezone
            now = dt.now(timezone.utc)
            hours = 96 if now.weekday() == 0 else 48
            emailer.send([], {"len_a": 0, "len_b": 0, "lookback_hours": hours},
                         test_mode=args.test)
            logging.info("=== Run complete (quiet day) ===")
            sys.exit(0)

        # 4. Pick papers
        selected = picker.pick_papers(query_a, query_b)
        logging.info(f"Selected {len(selected)} papers: "
                     f"{[(p['arxiv_id'], p['track']) for p in selected]}")

        # 5. Fetch full texts
        selected = reader.fetch_full_texts(selected)
        for p in selected:
            logging.info(f"  {p['arxiv_id']}: text_source={p['text_source']}")

        # 6. Summarize
        selected = summarizer.summarize_all(selected)

        # 7. Stats
        stats = {"len_a": len(query_a), "len_b": len(query_b)}

        # 8. DB + email
        if args.test:
            emailer.send(selected, stats)  # real send, no DB write
            logging.info("Test complete. Email sent via gateway. DB not updated.")
            if selected:
                print("\n--- SELECTED PAPERS SUMMARY ---")
                for p in selected:
                    print(f"\narxiv_id:    {p['arxiv_id']}")
                    print(f"title:       {p['title']}")
                    print(f"track:       {p['track']}")
                    print(f"text_source: {p['text_source']}")
                    print(f"summary:     {p.get('summary', '')[:300]}")
                    print("-" * 60)
        else:
            db.log_papers(query_a + query_b,
                          [p["arxiv_id"] for p in selected],
                          db_path)
            emailer.send(selected, stats)
            logging.info(f"Email sent to {os.getenv('MY_EMAIL')}")

        logging.info("=== Run complete ===")

    except Exception:
        tb = traceback.format_exc()
        logging.error(f"Unhandled exception:\n{tb}")
        try:
            import emailer
            emailer.send_failure(tb, test_mode=args.test)
        except Exception:
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()
