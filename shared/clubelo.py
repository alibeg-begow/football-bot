import requests
import csv
import logging
import io

logger = logging.getLogger("clubelo")
BASE_URL = "http://api.clubelo.com"

def team_elo(home_team, away_team, date_str):
    try:
        url = f"{BASE_URL}/{date_str}"
        resp = requests.get(url, timeout=15)
        if resp.status_code != 200:
            return None
            
        csv_data = resp.text
        reader = csv.DictReader(io.StringIO(csv_data))
        
        home_elo = None
        away_elo = None
        
        for row in reader:
            club = row.get("Club", "").lower()
            if home_team.lower() in club or club in home_team.lower():
                home_elo = float(row.get("Elo", 0))
            if away_team.lower() in club or club in away_team.lower():
                away_elo = float(row.get("Elo", 0))
                
            if home_elo and away_elo:
                break
                
        if home_elo and away_elo:
            win_prob = 1 / (1 + 10**((away_elo - home_elo) / 400))
            return {
                "home_elo": home_elo,
                "away_elo": away_elo,
                "home_win_prob": round(win_prob * 100, 1)
            }
            
    except Exception as e:
        logger.error(f"Error fetching clubelo: {e}")
        
    return None
