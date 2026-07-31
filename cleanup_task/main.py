import sys
import os
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

# add project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.db import init_db, get_connection
from shared.config_loader import CONFIG

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(PROJECT_ROOT, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, "cleanup.log"), encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("cleanup")

TZ = ZoneInfo(CONFIG["timezone"])

def get_today_start():
    # get 00:00 time of today
    now = datetime.now(TZ)
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return int(start_of_day.timestamp()), start_of_day

def main(dry_run=False):
    # run cleanup
    logger.info("Starting cleanup task")
    init_db()

    limit_ts, start_of_day = get_today_start()
    logger.info(f"Deleting matches started before {start_of_day}")

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT match_id, home_team, away_team, match_date "
        "FROM matches WHERE start_timestamp_utc < ?",
        (limit_ts,),
    )
    to_delete = cursor.fetchall()

    if not to_delete:
        logger.info("No matches to delete.")
        conn.close()
        logger.info("Cleanup task finished.")
        return 0

    logger.info(f"Found {len(to_delete)} matches to delete.")
    
    for m in to_delete:
        logger.info(f"Will delete: {m['home_team']} vs {m['away_team']} ({m['match_date']})")

    if dry_run:
        logger.info("Dry run enabled, skipping delete.")
        conn.close()
        return len(to_delete)

    # delete data
    ids = [m["match_id"] for m in to_delete]
    placeholders = ",".join("?" * len(ids))

    cursor.execute(f"DELETE FROM match_analysis WHERE match_id IN ({placeholders})", ids)
    deleted_analysis = cursor.rowcount
    
    cursor.execute(f"DELETE FROM match_details WHERE match_id IN ({placeholders})", ids)
    deleted_details = cursor.rowcount
    
    cursor.execute(f"DELETE FROM matches WHERE match_id IN ({placeholders})", ids)
    deleted_matches = cursor.rowcount

    conn.commit()

    # clean database space
    try:
        conn.execute("VACUUM")
    except Exception as e:
        logger.warning(f"Vacuum failed: {e}")

    conn.close()

    logger.info(f"Deleted {deleted_matches} matches.")
    logger.info(f"Deleted {deleted_details} details.")
    logger.info(f"Deleted {deleted_analysis} analysis.")
    logger.info("Cleanup task finished.")
    return deleted_matches

if __name__ == "__main__":
    main()
