import sys
import os
import json
import time
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# add project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.db import init_db, get_connection
from shared.config_loader import CONFIG
from shared import sofascore, weather, espn, news, prediction_model
from shared import football_data_uk, understat_xg, clubelo

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
logger = logging.getLogger("scraper2")

TZ = ZoneInfo(CONFIG["timezone"])
STYLE_THRESHOLDS = CONFIG["playing_style_thresholds"]
ESPN_SLUGS = {league["id"]: league.get("espn_slug") for league in CONFIG["leagues"]}

def get_play_style(stats):
    # determine team play style based on stats
    if not stats:
        return "Unknown"

    possession = stats.get("avg_possession")
    fouls = stats.get("fouls_per_match")

    if possession is None or fouls is None:
        return "Unknown"

    high_possession = STYLE_THRESHOLDS["possession_high"]
    low_possession = STYLE_THRESHOLDS["possession_low"]
    high_fouls = STYLE_THRESHOLDS["fouls_high"]

    if possession >= high_possession:
        style = "Possession / Attacking"
    elif possession <= low_possession:
        style = "Counter Attack"
    elif fouls is not None and fouls >= high_fouls:
        style = "High Pressing / Aggressive"
    else:
        style = "Balanced"

    extras = []
    counter_goals = stats.get("counter_attack_goals", 0)
    if isinstance(counter_goals, (int, float)) and counter_goals >= 3:
        extras.append("good counter attacks")
        
    header_goals = stats.get("header_goals", 0)
    if isinstance(header_goals, (int, float)) and header_goals >= 4:
        extras.append("strong on set pieces")
        
    long_shots = stats.get("long_shots", 0)
    if isinstance(long_shots, (int, float)) and long_shots >= 3:
        extras.append("long shot threat")

    if extras:
        return f"{style} ({', '.join(extras)})"
    return style

def get_data_quality(rich_data):
    # calculate data quality score (0-100)
    weights = {
        "referee_info": 15, "home_season_stats": 15, "away_season_stats": 15,
        "base_prediction": 15, "pregame_form": 10, "odds": 10,
        "h2h": 5, "team_streaks": 5, "standings": 5, "weather_data": 5,
    }
    score = sum(weight for key, weight in weights.items() if rich_data.get(key))
    return min(100, score)

def process_match(match):
    # process a single match and get all details
    match_id = match["match_id"]
    home_team = match["home_team"]
    away_team = match["away_team"]
    home_team_id = match["home_team_id"]
    away_team_id = match["away_team_id"]
    league_id = match["league_id"]
    espn_slug = ESPN_SLUGS.get(league_id)

    rich_data = {}

    event = sofascore.event_details(match_id)
    referee_info = sofascore.referee_info(event) if event else None
    stadium_info = sofascore.stadium_info(event) if event else None

    season_id = ((event.get("season") or {}).get("id")) if event else None
    ut_id = (((event.get("tournament") or {}).get("uniqueTournament") or {}).get("id")) if event else None
    custom_id = event.get("customId") if event else None

    if referee_info:
        rich_data["referee_info"] = referee_info
    if stadium_info:
        rich_data["stadium_info"] = stadium_info

    lineup_info = sofascore.lineup_info(match_id)

    home_coach = sofascore.team_coach(home_team_id)
    away_coach = sofascore.team_coach(away_team_id)

    h2h = sofascore.h2h_summary(match_id)
    if h2h:
        rich_data["h2h"] = h2h
        
    h2h_recent = sofascore.h2h_recent_matches(custom_id)
    if h2h_recent:
        rich_data["h2h_recent"] = h2h_recent

    form = sofascore.pregame_form(match_id)
    if form:
        rich_data["pregame_form"] = form

    odds = sofascore.odds(match_id)
    if odds:
        rich_data["odds"] = odds

    streaks = sofascore.team_streaks(match_id)
    if streaks:
        rich_data["team_streaks"] = streaks

    home_season_stats = sofascore.team_season_stats(home_team_id, ut_id, season_id)
    away_season_stats = sofascore.team_season_stats(away_team_id, ut_id, season_id)
    if home_season_stats:
        rich_data["home_season_stats"] = home_season_stats
    if away_season_stats:
        rich_data["away_season_stats"] = away_season_stats

    home_recent = sofascore.team_recent_matches(home_team_id)
    away_recent = sofascore.team_recent_matches(away_team_id)
    if home_recent:
        rich_data["home_recent_matches"] = home_recent
    if away_recent:
        rich_data["away_recent_matches"] = away_recent

    standings = sofascore.standings(ut_id, season_id, home_team, away_team)
    if standings:
        rich_data["standings"] = standings

    if stadium_info and stadium_info.get("latitude"):
        weather_data = weather.get_weather(
            stadium_info["latitude"], stadium_info["longitude"], match["start_timestamp_utc"]
        )
        if weather_data:
            rich_data["weather_data"] = weather_data

    postponed = False
    if espn_slug:
        date_espn = datetime.fromtimestamp(match["start_timestamp_utc"], tz=TZ).strftime("%Y%m%d")
        espn_match = espn.cross_validate_match(espn_slug, date_espn, home_team, away_team)
        if espn_match:
            rich_data["espn_validation"] = espn_match
            if espn_match.get("postponed"):
                postponed = True

        for side, team_name in [("home", home_team), ("away", away_team)]:
            injuries = espn.get_injury_list(espn_slug, team_name)
            if injuries:
                rich_data[f"{side}_injuries"] = injuries

    home_news = news.get_team_news(home_team, espn_slug)
    away_news = news.get_team_news(away_team, espn_slug)

    home_style = get_play_style(home_season_stats)
    away_style = get_play_style(away_season_stats)

    league_id = match["league_id"] if "league_id" in match.keys() else None
    
    base_prediction = prediction_model.generate_base_prediction(home_season_stats, away_season_stats, referee_info, league_id)
    if base_prediction:
        rich_data["statistical_base_model"] = base_prediction

    date_str = datetime.fromtimestamp(match["start_timestamp_utc"], tz=TZ).strftime("%Y-%m-%d")
    elo = clubelo.team_elo(home_team, away_team, date_str)
    if elo:
        rich_data["elo_ratings"] = elo

    league_info = next((l for l in CONFIG.get("leagues", []) if l["id"] == league_id), None)
    understat_slug = (league_info or {}).get("understat_slug")
    if understat_slug:
        xg = understat_xg.team_xg(home_team, away_team, understat_slug)
        if xg:
            rich_data["understat_xg"] = xg

    fduk_code = (league_info or {}).get("fduk_code")
    if fduk_code:
        fduk = football_data_uk.league_averages(fduk_code)
        if fduk:
            rich_data["fduk_league_averages"] = fduk

    # build final detail dict
    detail = {
        "match_id": match_id,
        "referee_name": referee_info.get("name") if referee_info else None,
        "referee_country": referee_info.get("country") if referee_info else None,
        "home_formation": lineup_info.get("home_formation") if lineup_info else None,
        "away_formation": lineup_info.get("away_formation") if lineup_info else None,
        "home_lineup_json": json.dumps(lineup_info.get("home_lineup", []) if lineup_info else [], ensure_ascii=False),
        "away_lineup_json": json.dumps(lineup_info.get("away_lineup", []) if lineup_info else [], ensure_ascii=False),
        "home_coach": home_coach,
        "away_coach": away_coach,
        "home_missing_players_json": json.dumps(lineup_info.get("home_missing", []) if lineup_info else [], ensure_ascii=False),
        "away_missing_players_json": json.dumps(lineup_info.get("away_missing", []) if lineup_info else [], ensure_ascii=False),
        "home_style_tag": home_style,
        "away_style_tag": away_style,
        "home_news_json": json.dumps(home_news, ensure_ascii=False),
        "away_news_json": json.dumps(away_news, ensure_ascii=False),
    }

    if lineup_info:
        rich_data["lineup_confirmed"] = lineup_info.get("confirmed", False)

    quality_score = get_data_quality(rich_data)
    detail["data_quality_score"] = quality_score
    detail["rich_data_json"] = json.dumps(rich_data, ensure_ascii=False)
    detail["fetched_at"] = datetime.now(timezone.utc).isoformat()

    return detail, rich_data, postponed


def main():
    # runner
    logger.info("Starting Detail Collector")
    init_db()

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT match_id, home_team, away_team, home_team_id, away_team_id, league_id, start_timestamp_utc
        FROM matches
        WHERE detail_fetched = 0 AND postponed = 0
    """)
    matches = cursor.fetchall()
    
    if not matches:
        logger.info("No matches waiting for details.")
        conn.close()
        return

    logger.info(f"Found {len(matches)} matches to process")
    processed = 0

    for match in matches:
        match_id = match["match_id"]
        home_team = match["home_team"]
        away_team = match["away_team"]
        
        logger.info(f"Processing: {home_team} vs {away_team}")
        
        try:
            detail, rich_data, postponed = process_match(match)
            
            if postponed:
                logger.warning(f"Match is postponed: {home_team} vs {away_team}")
                cursor.execute("UPDATE matches SET postponed = 1 WHERE match_id = ?", (match_id,))
            else:
                cursor.execute("""
                    INSERT OR REPLACE INTO match_details (
                        match_id, referee_name, referee_country,
                        home_formation, away_formation, home_lineup_json, away_lineup_json,
                        home_coach, away_coach,
                        home_missing_players_json, away_missing_players_json,
                        home_style_tag, away_style_tag,
                        home_news_json, away_news_json,
                        rich_data_json, data_quality_score, fetched_at
                    ) VALUES (
                        :match_id, :referee_name, :referee_country,
                        :home_formation, :away_formation, :home_lineup_json, :away_lineup_json,
                        :home_coach, :away_coach,
                        :home_missing_players_json, :away_missing_players_json,
                        :home_style_tag, :away_style_tag,
                        :home_news_json, :away_news_json,
                        :rich_data_json, :data_quality_score, :fetched_at
                    )
                """, detail)
                
                cursor.execute("UPDATE matches SET detail_fetched = 1 WHERE match_id = ?", (match_id,))
                
            conn.commit()
            processed += 1
            
        except Exception as e:
            logger.error(f"Error processing match {match_id}: {e}")
            
        time.sleep(1)

    conn.close()
    logger.info(f"Detail Collector finished. Processed {processed} matches.")

if __name__ == "__main__":
    main()
