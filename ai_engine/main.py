import sys
import os
import json
import logging
import sqlite3
from datetime import datetime, timezone
import traceback
import requests

# add project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.db import get_connection
from shared.config_loader import CONFIG, NVIDIA_API_KEY, GEMINI_API_KEY
from shared.http_client import get_data
from ai_engine.prompt_template import MAIN_PROMPT_TEMPLATE

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(PROJECT_ROOT, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, "ai.log"), encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("ai_engine")

def load_json(val):
    # load json safely
    if not val:
        return None
    if isinstance(val, (dict, list)):
        return val
    try:
        return json.loads(val)
    except Exception:
        return None

def format_form(form_list):
    # 'W','D','L' format
    if not form_list:
        return None
    return "-".join(form_list)

def build_team_block(row, side, rich_data):
    # build text for one team
    lines = []
    prefix = "home" if side == "home" else "away"
    team_name = row[f"{prefix}_team"]

    lines.append(f"--- {team_name.upper()} ({side.upper()}) ---")
    lines.append(f"Coach: {row[f'{prefix}_coach'] or 'Unknown'}")
    lines.append(f"Formation: {row[f'{prefix}_formation'] or 'Unknown'}")
    lines.append(f"Play Style: {row[f'{prefix}_style_tag'] or 'Unknown'}")

    lineup_info = load_json(row[f"{prefix}_lineup_json"]) or []
    starting_11 = [p["name"] for p in lineup_info if not p.get("substitute")]
    
    if starting_11:
        confirmed = rich_data.get("lineup_confirmed")
        tag = "Starting 11 (CONFIRMED)" if confirmed else "Starting 11 (Predicted)"
        lines.append(f"{tag}: {', '.join(starting_11)}")
    else:
        lines.append("Starting 11: Not announced")

    form_data = (rich_data.get("pregame_form") or {}).get(side)
    if form_data:
        streak = format_form(form_data.get("form"))
        if streak:
            lines.append(f"Last 5 Matches Form: {streak}")
        if form_data.get("league_position"):
            lines.append(f"League Position: {form_data['league_position']} ({form_data.get('points')} points)")
        if form_data.get("avg_rating"):
            lines.append(f"Average Rating: {form_data['avg_rating']}")

    missing = load_json(row[f"{prefix}_missing_players_json"]) or []
    if missing:
        lines.append("\nMissing Players:")
        for m in missing:
            reason = m.get('reason', 'Unknown')
            lines.append(f"  - {m['name']} ({m.get('position', 'Unknown')}): {reason}")
    else:
        lines.append("\nMissing Players: None reported")

    news_list = load_json(row[f"{prefix}_news_json"]) or []
    if news_list:
        lines.append("\nTeam News:")
        for n in news_list[:3]:
            lines.append(f"  - {n.get('title', '')}")

    stats = rich_data.get(f"{prefix}_season_stats")
    if stats:
        lines.append("\nSeason Stats (Per Match):")
        lines.append(f"  Goals Scored: {stats.get('goals_scored_per_match', 'N/A')}")
        lines.append(f"  Goals Conceded: {stats.get('goals_conceded_per_match', 'N/A')}")
        lines.append(f"  xG: {stats.get('xg_per_match', 'N/A')} | xGA: {stats.get('xga_per_match', 'N/A')}")
        lines.append(f"  Corners: {stats.get('corners_per_match', 'N/A')}")
        lines.append(f"  Fouls: {stats.get('fouls_per_match', 'N/A')}")
        lines.append(f"  Ball Possession: %{stats.get('avg_possession', 'N/A')}")

    return "\n".join(lines)

def build_match_data(row):
    # build the full match data string for the prompt
    rich_data = load_json(row["rich_data_json"]) or {}
    
    lines = []
    lines.append(f"MATCH: {row['home_team']} vs {row['away_team']}")
    lines.append(f"LEAGUE: {row['league_name']}")
    lines.append(f"DATE: {row['match_date']} {row['match_time']}")
    lines.append("="*40)

    # 1. Base Model
    base_model = rich_data.get("statistical_base_model")
    if base_model:
        lines.append("\n[STATISTICAL BASE MODEL (Poisson & Averages)]")
        lines.append("Goal Expectations:")
        lines.append(f"  Home: {base_model.get('expected_home_goals')} | Away: {base_model.get('expected_away_goals')} | Total: {base_model.get('expected_total_goals')}")
        lines.append("Probabilities:")
        lines.append(f"  Home Win: %{base_model.get('home_win_prob')} | Draw: %{base_model.get('draw_prob')} | Away Win: %{base_model.get('away_win_prob')}")
        lines.append(f"  Over 2.5: %{base_model.get('over_2_5_prob')} | Under 2.5: %{base_model.get('under_2_5_prob')}")
        lines.append(f"  BTTS Yes: %{base_model.get('btts_yes_prob')} | BTTS No: %{base_model.get('btts_no_prob')}")
        lines.append(f"Expected Scoreline: {base_model.get('most_likely_score')}")
        lines.append("Card Expectations (Referee + Team tendencies):")
        lines.append(f"  Total Cards: {base_model.get('expected_total_cards')}")
        lines.append(f"  Home Cards: {base_model.get('expected_home_cards')} | Away Cards: {base_model.get('expected_away_cards')}")
        lines.append("Other:")
        lines.append(f"  Corners: {base_model.get('expected_corners')} | Fouls: {base_model.get('expected_fouls')} | Offsides: {base_model.get('expected_offsides')}")

    # 2. Odds
    odds = rich_data.get("odds")
    if odds:
        lines.append("\n[BOOKMAKER ODDS]")
        lines.append(f"  1: {odds.get('home_win')} | X: {odds.get('draw')} | 2: {odds.get('away_win')}")
        lines.append(f"  Over 2.5: {odds.get('over_2_5')} | Under 2.5: {odds.get('under_2_5')}")
        lines.append(f"  BTTS Yes: {odds.get('btts_yes')} | BTTS No: {odds.get('btts_no')}")

    # 3. Weather & Referee
    lines.append("\n[MATCH CONDITIONS]")
    ref = row['referee_name']
    lines.append(f"Referee: {ref if ref else 'Unknown'}")
    
    weather = rich_data.get("weather_data")
    if weather:
        lines.append(f"Weather: {weather.get('condition', 'Unknown')}, {weather.get('temp_c', '?')}°C")
    else:
        lines.append("Weather: Unknown")

    # 4. H2H
    h2h = rich_data.get("h2h")
    if h2h:
        lines.append("\n[HEAD TO HEAD (Last Matches)]")
        lines.append(f"  Home Wins: {h2h.get('home_wins')} | Draws: {h2h.get('draws')} | Away Wins: {h2h.get('away_wins')}")

    # 5. Teams
    lines.append("\n[TEAM DETAILS]")
    lines.append(build_team_block(row, "home", rich_data))
    lines.append("")
    lines.append(build_team_block(row, "away", rich_data))

    return "\n".join(lines)

def call_nvidia_nim(prompt):
    # call nvidia api
    url = "https://integrate.api.nvidia.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {NVIDIA_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": CONFIG.get("nvidia_model", "z-ai/glm-5.2"),
        "messages": [{"role": "user", "content": prompt}],
        "temperature": CONFIG.get("ai_temperature", 0.4),
        "max_tokens": CONFIG.get("ai_max_tokens", 4096)
    }
    
    logger.info("Calling NVIDIA API...")
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error(f"NVIDIA API Error: {e}")
        return None

def process_matches():
    # process all pending matches
    conn = get_connection()
    cursor = conn.cursor()
    
    # get matches that have details but no analysis
    cursor.execute("""
        SELECT m.match_id, m.home_team, m.away_team, m.league_name, m.match_date, m.match_time,
               d.referee_name, d.home_coach, d.away_coach, d.home_formation, d.away_formation,
               d.home_lineup_json, d.away_lineup_json, d.home_style_tag, d.away_style_tag,
               d.home_missing_players_json, d.away_missing_players_json, d.home_news_json, d.away_news_json,
               d.rich_data_json
        FROM matches m
        JOIN match_details d ON m.match_id = d.match_id
        WHERE m.detail_fetched = 1 AND m.analysis_done = 0
    """)
    matches = cursor.fetchall()
    
    if not matches:
        logger.info("No matches waiting for analysis.")
        conn.close()
        return

    logger.info(f"Found {len(matches)} matches to analyze.")
    
    for row in matches:
        match_id = row["match_id"]
        logger.info(f"Analyzing match: {row['home_team']} vs {row['away_team']}")
        
        match_text = build_match_data(row)
        prompt = MAIN_PROMPT_TEMPLATE.replace("[DATA_PLACEHOLDER]", match_text)
        
        # generate analysis
        analysis = call_nvidia_nim(prompt)
        
        if analysis:
            now_str = datetime.now(timezone.utc).isoformat()
            cursor.execute("""
                INSERT OR REPLACE INTO match_analysis (match_id, analysis_text, model_used, generated_at)
                VALUES (?, ?, ?, ?)
            """, (match_id, analysis, CONFIG.get("nvidia_model", "nvidia"), now_str))
            
            cursor.execute("UPDATE matches SET analysis_done = 1 WHERE match_id = ?", (match_id,))
            conn.commit()
            logger.info("Analysis saved.")
        else:
            logger.error("Failed to generate analysis.")

    conn.close()
    logger.info("AI engine finished.")

def main():
    # main runner
    if not NVIDIA_API_KEY:
        logger.error("NVIDIA_API_KEY is missing in .env")
        return
        
    logger.info("Starting AI Engine")
    try:
        process_matches()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    main()
