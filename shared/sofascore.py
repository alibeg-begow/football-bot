import logging
from shared.http_client import get_data
from shared.config_loader import CONFIG

logger = logging.getLogger("sofascore")
BASE = CONFIG["sofascore_base_url"]

def event_details(match_id):
    # get raw event object
    d = get_data(f"{BASE}/event/{match_id}")
    if not d:
        return {}
    return d.get("event", d) if isinstance(d, dict) else {}

def referee_info(event):
    # get referee name, country and card stats
    ref = event.get("referee") or {}
    if not ref:
        return None

    games = ref.get("games") or 0
    yellows = ref.get("yellowCards") or 0
    reds = ref.get("redCards") or 0
    second_yellows = ref.get("yellowRedCards") or 0

    info = {
        "name": ref.get("name"),
        "country": (ref.get("country") or {}).get("name"),
        "total_games": games,
        "total_yellows": yellows,
        "total_reds": reds + second_yellows,
    }

    if games and games > 0:
        info["yellows_per_match"] = round(yellows / games, 2)
        info["reds_per_match"] = round((reds + second_yellows) / games, 3)
    else:
        info["yellows_per_match"] = None
        info["reds_per_match"] = None

    return info

def stadium_info(event):
    # get stadium name, city, capacity and coords
    venue = event.get("venue") or {}
    if not venue:
        return None
    coords = venue.get("venueCoordinates") or {}
    return {
        "name": venue.get("name"),
        "city": (venue.get("city") or {}).get("name"),
        "capacity": venue.get("capacity"),
        "latitude": coords.get("latitude"),
        "longitude": coords.get("longitude"),
    }

def h2h_summary(match_id):
    # get h2h win distribution
    d = get_data(f"{BASE}/event/{match_id}/h2h")
    if not d or not isinstance(d, dict):
        return None
    duel = d.get("teamDuel") or {}
    if not duel:
        return None
    return {
        "home_wins": duel.get("homeWins", 0),
        "away_wins": duel.get("awayWins", 0),
        "draws": duel.get("draws", 0),
        "total": (duel.get("homeWins", 0) + duel.get("awayWins", 0) + duel.get("draws", 0)),
    }

def h2h_recent_matches(custom_id, limit=5):
    # get past h2h match scores
    if not custom_id:
        return []
    d = get_data(f"{BASE}/event/{custom_id}/h2h/events")
    if not d or not isinstance(d, dict):
        return []

    matches = []
    for e in (d.get("events") or [])[-limit:]:
        try:
            matches.append({
                "date": e.get("startTimestamp"),
                "home": e["homeTeam"]["name"],
                "away": e["awayTeam"]["name"],
                "score": f"{e.get('homeScore', {}).get('current')}-{e.get('awayScore', {}).get('current')}",
            })
        except (KeyError, TypeError):
            continue
    return matches

def pregame_form(match_id):
    # get pregame form: last 5 results, league position, avg rating
    d = get_data(f"{BASE}/event/{match_id}/pregame-form")
    if not d or not isinstance(d, dict):
        return None

    def extract(side):
        t = d.get(side) or {}
        if not t:
            return None
        return {
            "form": t.get("form", []),
            "league_position": t.get("position"),
            "points": t.get("value"),
            "avg_rating": t.get("avgRating"),
        }

    return {
        "home": extract("homeTeam"),
        "away": extract("awayTeam"),
        "label": d.get("label"),
    }

def team_streaks(match_id):
    # get team streaks (over 2.5, btts etc)
    d = get_data(f"{BASE}/event/{match_id}/team-streaks")
    if not d or not isinstance(d, dict):
        return None

    def extract(section):
        out = []
        for s in (d.get(section) or []):
            out.append({
                "name": s.get("name"),
                "value": s.get("value"),
                "team": s.get("team"),
            })
        return out

    general = extract("general")
    h2h = extract("head2head")
    if not general and not h2h:
        return None
    return {"general": general, "h2h": h2h}

def _fraction_to_decimal(fraction):
    # convert fractional odds to decimal
    try:
        if "/" in str(fraction):
            num, den = str(fraction).split("/")
            return (float(num) / float(den)) + 1.0
        return float(fraction) + 1.0
    except (ValueError, ZeroDivisionError, AttributeError):
        return None

def odds(match_id):
    # get betting odds and convert to market probabilities
    d = get_data(f"{BASE}/event/{match_id}/odds/1/all")
    if not d or not isinstance(d, dict):
        return None

    result = {}
    for market in (d.get("markets") or []):
        market_name = market.get("marketName", "")
        choices = market.get("choices") or []

        if market.get("marketId") == 1 or market_name == "Full time":
            decimals = {}
            for c in choices:
                name = c.get("name")
                dec = _fraction_to_decimal(c.get("fractionalValue"))
                if name and dec:
                    decimals[name] = dec

            if len(decimals) == 3:
                raw = {k: 1.0 / v for k, v in decimals.items()}
                total = sum(raw.values())
                result["match_result"] = {
                    "home_win": round(100 * raw.get("1", 0) / total, 1),
                    "draw": round(100 * raw.get("X", 0) / total, 1),
                    "away_win": round(100 * raw.get("2", 0) / total, 1),
                    "odds": {k: round(v, 2) for k, v in decimals.items()},
                    "bookmaker_margin": round(100 * (total - 1), 1),
                }

        elif "total" in market_name.lower() or market.get("marketId") == 3:
            for c in choices:
                name = (c.get("name") or "").lower()
                dec = _fraction_to_decimal(c.get("fractionalValue"))
                if not dec:
                    continue
                if "over" in name:
                    result.setdefault("total_goals", {})["over_odds"] = round(dec, 2)
                    result["total_goals"]["line"] = market.get("choiceGroup")
                elif "under" in name:
                    result.setdefault("total_goals", {})["under_odds"] = round(dec, 2)

        elif "both teams" in market_name.lower():
            for c in choices:
                name = (c.get("name") or "").lower()
                dec = _fraction_to_decimal(c.get("fractionalValue"))
                if not dec:
                    continue
                if name in ("yes", "evet"):
                    result.setdefault("btts", {})["yes_odds"] = round(dec, 2)
                elif name in ("no", "hayir"):
                    result.setdefault("btts", {})["no_odds"] = round(dec, 2)

    tg = result.get("total_goals")
    if tg and tg.get("over_odds") and tg.get("under_odds"):
        ho, hu = 1 / tg["over_odds"], 1 / tg["under_odds"]
        t = ho + hu
        tg["over_prob"] = round(100 * ho / t, 1)
        tg["under_prob"] = round(100 * hu / t, 1)

    btts = result.get("btts")
    if btts and btts.get("yes_odds") and btts.get("no_odds"):
        hy, hn = 1 / btts["yes_odds"], 1 / btts["no_odds"]
        t = hy + hn
        btts["yes_prob"] = round(100 * hy / t, 1)
        btts["no_prob"] = round(100 * hn / t, 1)

    return result or None

def team_season_stats(team_id, unique_tournament_id, season_id):
    # get team season stats as per-match averages
    if not (team_id and unique_tournament_id and season_id):
        return None

    url = (f"{BASE}/team/{team_id}/unique-tournament/{unique_tournament_id}"
           f"/season/{season_id}/statistics/overall")
    d = get_data(url)
    s = d.get("statistics") if isinstance(d, dict) else {}
    games = s.get("matches") or 0
    
    if not games:
        recent = team_recent_matches(team_id, limit=10)
        if recent:
            return {
                "played_matches": len(recent["matches"]),
                "goals_scored_per_match": recent["goals_scored_per_match"],
                "goals_conceded_per_match": recent["goals_conceded_per_match"],
                "fallback_used": True
            }
        return None

    def avg(key, decimals=2):
        v = s.get(key)
        return round(v / games, decimals) if isinstance(v, (int, float)) else None

    def raw(key):
        return s.get(key)

    def pct(key, decimals=1):
        v = s.get(key)
        return round(v, decimals) if isinstance(v, (int, float)) else None

    stats = {
        "played_matches": games,

        "goals_scored_per_match": avg("goalsScored"),
        "shots_per_match": avg("shots"),
        "shots_on_target_per_match": avg("shotsOnTarget"),
        "big_chances_per_match": avg("bigChancesCreated"),
        "big_chances_missed_per_match": avg("bigChancesMissed"),
        "box_shots_per_match": avg("shotsFromInsideTheBox"),

        "goals_conceded_per_match": avg("goalsConceded"),
        "shots_against_per_match": avg("shotsAgainst"),
        "shots_on_target_against_per_match": avg("shotsOnTargetAgainst"),
        "big_chances_against_per_match": avg("bigChancesAgainst"),
        "clean_sheets": raw("cleanSheets"),
        "errors_leading_to_goal_per_match": avg("errorsLeadingToGoal", 3),

        "corners_per_match": avg("corners"),
        "corners_against_per_match": avg("cornersAgainst"),

        "offsides_per_match": avg("offsides"),
        "offsides_against_per_match": avg("offsidesAgainst"),

        "fouls_per_match": avg("fouls"),
        "yellows_per_match": avg("yellowCards"),
        "yellows_against_per_match": avg("yellowCardsAgainst"),
        "total_reds": raw("redCards"),
        "total_second_yellows": raw("yellowRedCards"),

        "penalties_won": raw("penaltiesTaken"),
        "penalties_conceded": raw("penaltiesCommited"),
        "penalty_goals": raw("penaltyGoals"),

        "avg_possession": pct("averageBallPossession"),
        "pass_accuracy_pct": pct("accuratePassesPercentage"),
        "counter_attacks_per_match": avg("fastBreaks"),
        "counter_attack_goals": raw("fastBreakGoals"),
        "header_goals": raw("headedGoals"),
        "long_shots": raw("goalsFromOutsideTheBox"),
        "duels_won_pct": pct("duelsWonPercentage"),
        "aerial_duels_won_pct": pct("aerialDuelsWonPercentage"),
        "tackles_per_match": avg("tackles"),
        "interceptions_per_match": avg("interceptions"),
        "avg_rating": pct("avgRating", 2),
    }

    for src, dst in [("expectedGoals", "xg_per_match"),
                      ("expectedGoalsAgainst", "xga_per_match")]:
        if isinstance(s.get(src), (int, float)):
            stats[dst] = round(s[src] / games, 2)

    return {k: v for k, v in stats.items() if v is not None}

def team_recent_matches(team_id, limit=8):
    # get recent match results
    d = get_data(f"{BASE}/team/{team_id}/events/last/0")
    if not d or not isinstance(d, dict):
        return None

    events = (d.get("events") or [])[-limit:]
    if not events:
        return None

    matches = []
    wins = draws = losses = 0
    scored = conceded = 0

    for e in reversed(events):
        try:
            home_id = e["homeTeam"]["id"]
            home_score = e.get("homeScore", {}).get("current")
            away_score = e.get("awayScore", {}).get("current")
            if home_score is None or away_score is None:
                continue

            is_home = (home_id == team_id)
            our_score = home_score if is_home else away_score
            opp_score = away_score if is_home else home_score
            opponent = e["awayTeam"]["name"] if is_home else e["homeTeam"]["name"]

            if our_score > opp_score:
                result = "W"
                wins += 1
            elif our_score == opp_score:
                result = "D"
                draws += 1
            else:
                result = "L"
                losses += 1

            scored += our_score
            conceded += opp_score

            matches.append({
                "opponent": opponent,
                "venue": "home" if is_home else "away",
                "score": f"{our_score}-{opp_score}",
                "result": result,
                "tournament": (e.get("tournament") or {}).get("name"),
            })
        except (KeyError, TypeError):
            continue

    if not matches:
        return None

    n = len(matches)
    return {
        "matches": matches,
        "form_string": "".join(m["result"] for m in matches),
        "wins": wins,
        "draws": draws,
        "losses": losses,
        "goals_scored_per_match": round(scored / n, 2),
        "goals_conceded_per_match": round(conceded / n, 2),
    }

def lineup_info(match_id):
    # get lineup, formation, missing players
    d = get_data(f"{BASE}/event/{match_id}/lineups")
    if not d or not isinstance(d, dict):
        return None

    def parse_players(player_list):
        out = []
        for p in player_list:
            player = p.get("player") or {}
            out.append({
                "name": player.get("name", "Unknown"),
                "position": p.get("position") or player.get("position", ""),
                "jersey": p.get("jerseyNumber"),
                "substitute": p.get("substitute", False),
                "rating": p.get("avgRating"),
            })
        return out

    def parse_missing(missing_list):
        out = []
        for m in missing_list:
            player = m.get("player") or {}
            reason_obj = m.get("reason")
            if isinstance(reason_obj, dict):
                reason = reason_obj.get("short") or reason_obj.get("name") or "unknown"
            else:
                reason = str(reason_obj) if reason_obj else "unknown"
            out.append({
                "name": player.get("name", "Unknown"),
                "reason": reason,
                "position": player.get("position", ""),
                "return_date": None,
            })
        return out

    home = d.get("home") or {}
    away = d.get("away") or {}

    return {
        "confirmed": d.get("confirmed", False),
        "home_formation": home.get("formation"),
        "away_formation": away.get("formation"),
        "home_lineup": parse_players(home.get("players") or []),
        "away_lineup": parse_players(away.get("players") or []),
        "home_missing": parse_missing(home.get("missingPlayers") or []),
        "away_missing": parse_missing(away.get("missingPlayers") or []),
    }

def team_coach(team_id):
    # get team coach name
    d = get_data(f"{BASE}/team/{team_id}")
    if not d or not isinstance(d, dict):
        return None
    team = d.get("team", d)
    return (team.get("manager") or {}).get("name")

def standings(unique_tournament_id, season_id, home_team, away_team):
    # get league standings
    if not (unique_tournament_id and season_id):
        return None

    url = (f"{BASE}/unique-tournament/{unique_tournament_id}"
           f"/season/{season_id}/standings/total")
    d = get_data(url)
    if not d or not isinstance(d, dict) or not d.get("standings"):
        return None

    try:
        rows = d["standings"][0].get("rows") or []
    except (IndexError, KeyError, TypeError):
        return None

    if not rows:
        return None

    def row_summary(r):
        return {
            "position": r.get("position"),
            "team": (r.get("team") or {}).get("name"),
            "played": r.get("matches"),
            "points": r.get("points"),
            "wins": r.get("wins"),
            "draws": r.get("draws"),
            "losses": r.get("losses"),
            "goals_for": r.get("scoresFor"),
            "goals_against": r.get("scoresAgainst"),
        }

    def find_team(name):
        search = (name or "").lower()
        for r in rows:
            t = ((r.get("team") or {}).get("name") or "").lower()
            if not t:
                continue
            if search == t or search in t or t in search:
                return row_summary(r)
        return None

    return {
        "total_teams": len(rows),
        "top_3": [row_summary(r) for r in rows[:3]],
        "home": find_team(home_team),
        "away": find_team(away_team),
    }
