import logging
from datetime import datetime
from shared.http_client import get_data

logger = logging.getLogger("espn")

SITE = "https://site.api.espn.com/apis/site/v2/sports/soccer"
WEB = "https://site.web.api.espn.com/apis/site/v2/sports/soccer"

def match_names(a, b):
    # fuzzy team name matching
    if not a or not b:
        return False
    a, b = a.lower().strip(), b.lower().strip()
    if a == b or a in b or b in a:
        return True
    
    stop_words = {"fc", "sc", "cf", "ac", "afc", "cd", "club", "de", "the", "united", "city"}
    a_parts = {w for w in a.split() if w not in stop_words and len(w) > 3}
    b_parts = {w for w in b.split() if w not in stop_words and len(w) > 3}
    return bool(a_parts & b_parts)

def get_league_news(espn_slug, limit=8):
    # get league news feed
    if not espn_slug:
        return []

    data = get_data(f"{SITE}/{espn_slug}/news")
    if not data or not isinstance(data, dict):
        return []

    news_list = []
    for article in (data.get("articles") or [])[:limit]:
        news_list.append({
            "title": article.get("headline"),
            "summary": article.get("description"),
            "date": (article.get("published") or "")[:10],
            "source": "ESPN",
        })
    return news_list

def get_team_news(espn_slug, team_name, limit=5):
    # get team specific news from league feed
    all_news = get_league_news(espn_slug, limit=30)
    related = []
    for h in all_news:
        text = f"{h.get('title') or ''} {h.get('summary') or ''}"
        if match_names(team_name, text) or (team_name or "").lower() in text.lower():
            related.append(h)
        if len(related) >= limit:
            break
    return related

def get_injury_list(espn_slug, team_name=None):
    # get injury list from espn
    if not espn_slug:
        return []

    data = get_data(f"{WEB}/{espn_slug}/injuries")
    if not data or not isinstance(data, dict):
        return []

    result = []
    for team in (data.get("injuries") or []):
        t_name = team.get("displayName") or ""
        if team_name and not match_names(team_name, t_name):
            continue
        for obj in (team.get("injuries") or []):
            player = (obj.get("athlete") or {}).get("displayName")
            status = obj.get("status")
            details = (obj.get("details") or {})
            result.append({
                "team": t_name,
                "name": player,
                "status": status,
                "type": details.get("type"),
                "return_date": details.get("returnDate"),
                "source": "ESPN",
            })
    return result

def cross_validate_match(espn_slug, date_yyyymmdd, home_team, away_team):
    # check espn for match postponement and independent odds
    if not espn_slug or not date_yyyymmdd:
        return None

    data = get_data(f"{SITE}/{espn_slug}/scoreboard?dates={date_yyyymmdd}")
    if not data or not isinstance(data, dict):
        return None

    for event in (data.get("events") or []):
        try:
            competition = (event.get("competitions") or [{}])[0]
            teams = competition.get("competitors") or []
            if len(teams) < 2:
                continue

            names = [(t.get("team") or {}).get("displayName", "") for t in teams]
            home_match = any(match_names(home_team, n) for n in names)
            away_match = any(match_names(away_team, n) for n in names)
            if not (home_match and away_match):
                continue

            status_obj = ((event.get("status") or {}).get("type") or {})
            result = {
                "status": status_obj.get("description"),
                "postponed": status_obj.get("name") in ("STATUS_POSTPONED", "STATUS_CANCELED"),
                "stadium": (competition.get("venue") or {}).get("fullName"),
                "source": "ESPN",
            }

            odds = competition.get("odds") or []
            if odds:
                odd = odds[0]
                result["odd"] = {
                    "provider": (odd.get("provider") or {}).get("name"),
                    "details": odd.get("details"),
                    "over_under": odd.get("overUnder"),
                }

            for t in teams:
                if t.get("form"):
                    side = "home" if t.get("homeAway") == "home" else "away"
                    result[f"{side}_form"] = t.get("form")

            return result
        except (KeyError, TypeError, IndexError):
            continue

    return None
