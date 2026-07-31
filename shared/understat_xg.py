import requests
from bs4 import BeautifulSoup
import json
import logging
import re

logger = logging.getLogger("understat_xg")

def team_xg(home_team, away_team, understat_slug):
    if not understat_slug:
        return None
        
    try:
        url = f"https://understat.com/league/{understat_slug}/2025"
        resp = requests.get(url, timeout=15)
        if resp.status_code != 200:
            # code
            url = f"https://understat.com/league/{understat_slug}/2024"
            resp = requests.get(url, timeout=15)
            if resp.status_code != 200:
                return None
            
        soup = BeautifulSoup(resp.content, "html.parser")
        scripts = soup.find_all("script")
        
        data = None
        for script in scripts:
            if script.string and "teamsData" in script.string:
                match = re.search(r"JSON\.parse\('([^']+)'\)", script.string)
                if match:
                    json_str = match.group(1).encode('utf-8').decode('unicode_escape')
                    data = json.loads(json_str)
                    break
                    
        if not data:
            return None
            
        home_data = None
        away_data = None
        
        for team_id, team in data.items():
            title = team.get("title", "").lower()
            if home_team.lower() in title or title in home_team.lower():
                home_data = team
            if away_team.lower() in title or title in away_team.lower():
                away_data = team
                
        if home_data and away_data:
            # code
            home_history = home_data.get("history", [])
            away_history = away_data.get("history", [])
            
            home_xg_avg = sum([h["xG"] for h in home_history]) / len(home_history) if home_history else None
            home_xga_avg = sum([h["xGA"] for h in home_history]) / len(home_history) if home_history else None
            
            away_xg_avg = sum([a["xG"] for a in away_history]) / len(away_history) if away_history else None
            away_xga_avg = sum([a["xGA"] for a in away_history]) / len(away_history) if away_history else None

            return {
                "home_xg_avg": round(home_xg_avg, 2) if home_xg_avg else None,
                "home_xga_avg": round(home_xga_avg, 2) if home_xga_avg else None,
                "away_xg_avg": round(away_xg_avg, 2) if away_xg_avg else None,
                "away_xga_avg": round(away_xga_avg, 2) if away_xga_avg else None
            }
            
    except Exception as e:
        logger.error(f"Error fetching understat: {e}")
        
    return None
