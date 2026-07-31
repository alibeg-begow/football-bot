import requests
import csv
import io
import logging

logger = logging.getLogger("football_data_uk")

_cache = {}

def league_averages(fduk_code):
    if not fduk_code:
        return None
        
    if fduk_code in _cache:
        return _cache[fduk_code]
        
    try:
        season = "2526"
        url = f"https://www.football-data.co.uk/mmz4281/{season}/{fduk_code}.csv"
        
        resp = requests.get(url, timeout=15)
        if resp.status_code != 200:
            # code
            season = "2425"
            url = f"https://www.football-data.co.uk/mmz4281/{season}/{fduk_code}.csv"
            resp = requests.get(url, timeout=15)
            if resp.status_code != 200:
                return None
            
        reader = csv.DictReader(io.StringIO(resp.text))
        
        total_goals = 0
        total_matches = 0
        
        for row in reader:
            try:
                fthg = int(row.get("FTHG", 0))
                ftag = int(row.get("FTAG", 0))
                total_goals += (fthg + ftag)
                total_matches += 1
            except ValueError:
                pass
                
        if total_matches > 0:
            avg = round(total_goals / total_matches, 2)
            _cache[fduk_code] = {"avg_goals_per_match": avg, "matches_played": total_matches}
            return _cache[fduk_code]
            
    except Exception as e:
        logger.error(f"Error fetching football-data.co.uk: {e}")
        
    return None
