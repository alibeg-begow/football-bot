import sys
import os
import time
import logging
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# add project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.db import init_db, get_connection
from shared.config_loader import CONFIG
from shared.http_client import get_data, print_stats

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(PROJECT_ROOT, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, "scraper.log"), encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("scraper1")

BASE_URL = CONFIG["sofascore_base_url"]
USER_AGENT = CONFIG["user_agent"]
DELAY = CONFIG["request_delay_seconds"]

# get league names
LEAGUE_IDS = {league["id"]: league["name"] for league in CONFIG["leagues"]}
TZ = ZoneInfo(CONFIG["timezone"])

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json",
}

def safe_request(url):
    # get data safely
    return get_data(url)

def get_target_date():
    # calculate tomorrow's date
    today = datetime.now(TZ)
    tomorrow = today + timedelta(days=1)
    return tomorrow.date()

def fetch_matches(target_date):
    # get all matches for the target date
    prev_day = target_date - timedelta(days=1)
    
    prev_day_str = prev_day.strftime("%Y-%m-%d")
    target_date_str = target_date.strftime("%Y-%m-%d")

    all_events = []
    
    for league_id, league_name in LEAGUE_IDS.items():
        url1 = f"{BASE_URL}/unique-tournament/{league_id}/scheduled-events/{prev_day_str}"
        url2 = f"{BASE_URL}/unique-tournament/{league_id}/scheduled-events/{target_date_str}"

        data1 = safe_request(url1)
        data2 = safe_request(url2)

        league_events = 0
        if isinstance(data1, dict) and "events" in data1:
            all_events.extend(data1["events"])
            league_events += len(data1["events"])
        if isinstance(data2, dict) and "events" in data2:
            all_events.extend(data2["events"])
            league_events += len(data2["events"])

        logger.info(f"League {league_name}: found {league_events} matches")

    logger.info(f"Total matches found: {len(all_events)}")
    return all_events

def filter_matches(events, target_date):
    # filter out matches that are not tomorrow
    filtered = []
    target_date_str = target_date.strftime("%d.%m.%Y")
    
    for event in events:
        try:
            ts = event.get("startTimestamp")
            if not ts:
                continue
                
            match_time_utc = datetime.fromtimestamp(ts, tz=ZoneInfo("UTC"))
            match_time_local = match_time_utc.astimezone(TZ)
            
            if match_time_local.date() == target_date:
                home_team = event["homeTeam"]["name"]
                away_team = event["awayTeam"]["name"]
                home_id = event["homeTeam"]["id"]
                away_id = event["awayTeam"]["id"]
                
                tour_id = event["tournament"]["uniqueTournament"]["id"]
                
                filtered.append({
                    "match_id": event["id"],
                    "home_team": home_team,
                    "away_team": away_team,
                    "home_id": home_id,
                    "away_id": away_id,
                    "league_id": tour_id,
                    "league_name": LEAGUE_IDS.get(tour_id, "Unknown"),
                    "match_date": target_date_str,
                    "match_time": match_time_local.strftime("%H:%M"),
                    "start_timestamp": ts
                })
        except Exception as e:
            logger.error("Error filtering match")
            
    return filtered

def save_matches_to_db(matches):
    # save matches to the database
    conn = get_connection()
    cursor = conn.cursor()
    
    added = 0
    now_str = datetime.now(ZoneInfo("UTC")).isoformat()
    
    for match in matches:
        cursor.execute("SELECT match_id FROM matches WHERE match_id = ?", (match["match_id"],))
        if not cursor.fetchone():
            cursor.execute("""
                INSERT INTO matches (
                    match_id, home_team, away_team, home_team_id, away_team_id,
                    league_id, league_name, match_date, match_time, start_timestamp_utc,
                    scraped_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                match["match_id"], match["home_team"], match["away_team"],
                match["home_id"], match["away_id"], match["league_id"],
                match["league_name"], match["match_date"], match["match_time"],
                match["start_timestamp"], now_str
            ))
            added += 1
            
    conn.commit()
    conn.close()
    logger.info(f"Saved {added} new matches to database")
    return added

def main():
    # main runner
    logger.info("Starting scraper_matches")
    init_db()
    
    target_date = get_target_date()
    logger.info(f"Target date is {target_date}")
    
    events = fetch_matches(target_date)
    matches = filter_matches(events, target_date)
    
    logger.info(f"Found {len(matches)} matches for the target date")
    
    save_matches_to_db(matches)
    
    print_stats()
    logger.info("Finished scraper_matches")

if __name__ == "__main__":
    main()
