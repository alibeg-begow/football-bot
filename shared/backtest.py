import sys
import os
import json
import logging
import math

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.db import get_connection
from shared.prediction_model import generate_base_prediction

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("backtest")

def calc_log_loss(y_true, y_pred):
    # log-loss, lower is better
    eps = 1e-15
    y_pred = max(eps, min(1 - eps, y_pred))
    return -(y_true * math.log(y_pred) + (1 - y_true) * math.log(1 - y_pred))

def calc_brier(y_true, y_pred):
    # brier score (0-1), lower is better
    return (y_pred - y_true) ** 2

def run_backtest():
    # run predictions against past results
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT m.match_id, m.home_score, m.away_score, m.league_id, md.rich_data_json
        FROM matches m
        JOIN match_details md ON m.match_id = md.match_id
        WHERE m.home_score IS NOT NULL AND m.away_score IS NOT NULL
    """)
    matches = cursor.fetchall()
    conn.close()

    if not matches:
        logger.warning("No completed matches found for backtest.")
        return

    total_brier = 0
    total_logloss = 0
    valid_count = 0
    correct_count = 0

    logger.info(f"Running backtest on {len(matches)} matches...")

    for row in matches:
        match_id = row["match_id"]
        h_score = row["home_score"]
        a_score = row["away_score"]
        league_id = row["league_id"]
        rich_json = row["rich_data_json"]

        if not rich_json:
            continue
            
        try:
            rich_data = json.loads(rich_json)
        except json.JSONDecodeError:
            continue

        home_stats = rich_data.get("home_season_stats") or rich_data.get("ev_sezon_istatistik")
        away_stats = rich_data.get("away_season_stats") or rich_data.get("deplasman_sezon_istatistik")
        referee_info = rich_data.get("referee_info")

        if not home_stats or not away_stats:
            continue

        base = generate_base_prediction(home_stats, away_stats, referee_info, league_id)
        if not base or "poisson_probabilities" not in base:
            continue

        poisson = base["poisson_probabilities"]
        p_home = poisson.get("home_win_pct", 0) / 100.0
        p_draw = poisson.get("draw_pct", 0) / 100.0
        p_away = poisson.get("away_win_pct", 0) / 100.0
        
        if p_home + p_draw + p_away == 0:
            continue

        y_home = 1 if h_score > a_score else 0
        y_draw = 1 if h_score == a_score else 0
        y_away = 1 if h_score < a_score else 0
        
        max_p = max(p_home, p_draw, p_away)
        if (max_p == p_home and y_home == 1) or \
           (max_p == p_draw and y_draw == 1) or \
           (max_p == p_away and y_away == 1):
            correct_count += 1

        brier = calc_brier(y_home, p_home) + calc_brier(y_draw, p_draw) + calc_brier(y_away, p_away)
        total_brier += brier

        if y_home:
            ll = -math.log(max(1e-15, p_home))
        elif y_draw:
            ll = -math.log(max(1e-15, p_draw))
        else:
            ll = -math.log(max(1e-15, p_away))
        
        total_logloss += ll
        valid_count += 1

    if valid_count == 0:
        logger.warning("No valid matches found for scoring.")
        return

    avg_brier = total_brier / valid_count
    avg_logloss = total_logloss / valid_count
    accuracy = (correct_count / valid_count) * 100

    logger.info(f"Backtest Results ({valid_count} matches)")
    logger.info(f"Avg Brier Score: {avg_brier:.4f}")
    logger.info(f"Avg Log-Loss: {avg_logloss:.4f}")
    logger.info(f"Accuracy: {accuracy:.1f}%")
    logger.info(f"Correct: {correct_count}/{valid_count}")

if __name__ == "__main__":
    run_backtest()
