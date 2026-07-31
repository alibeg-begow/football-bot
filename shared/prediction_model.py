import math
import logging
from shared.config_loader import CONFIG

logger = logging.getLogger("prediction_model")

MODEL = CONFIG.get("model_parametreleri", {})
HOME_ADVANTAGE = MODEL.get("ev_sahibi_avantaji", 1.12)
AWAY_MULTIPLIER = MODEL.get("deplasman_carpani", 0.92)
REFEREE_WEIGHT = MODEL.get("hakem_agirligi", 0.5)
MAX_GOALS = 8

def _shrink(stats_dict, key, league_avg, k=None):
    # empirical bayes shrinkage toward league average
    if k is None:
        k = MODEL.get("shrinkage_k", 8)
    if not stats_dict:
        return None
    val = stats_dict.get(key)
    played = stats_dict.get("played_matches")
    if not isinstance(val, (int, float)) or not isinstance(played, (int, float)) or played <= 0:
        return val
    return (played * val + k * league_avg) / (played + k)

def _blend(produced, allowed):
    # blend team's production with opponent's allowance
    values = [v for v in (produced, allowed) if isinstance(v, (int, float))]
    if not values:
        return None
    return sum(values) / len(values)

def _poisson_pmf(k, lam):
    # P(X = k) poisson
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    try:
        return (lam ** k) * math.exp(-lam) / math.factorial(k)
    except (OverflowError, ValueError):
        return 0.0

def _poisson_cdf(k, lam):
    # P(X <= k) poisson cdf
    return sum(_poisson_pmf(i, lam) for i in range(k + 1))

def _confidence_interval(lam, dispersion=1.0, played_matches=None):
    # 10-90% confidence interval
    if lam <= 0:
        return 0, 0
        
    variance = lam * dispersion
    if played_matches and played_matches > 0:
        variance += (lam / played_matches)
        
    std = math.sqrt(variance)
    low = max(0, int(math.floor(lam - 1.28 * std)))
    high = int(math.ceil(lam + 1.28 * std))
    return low, high

def _safe_get(d, key, fallback_key=None):
    # get value from dict, avoiding 0 being treated as falsy
    val = d.get(key)
    if val is not None:
        return val
    if fallback_key:
        return d.get(fallback_key)
    return None

def calc_expected_goals(home_stats, away_stats, league_id=None):
    # calculate expected goals for both teams
    if not home_stats or not away_stats:
        return None, None

    league_info = {}
    if league_id:
        for l in CONFIG.get("leagues", []):
            if l.get("id") == league_id:
                league_info = l
                break
                
    ha = league_info.get("home_advantage", HOME_ADVANTAGE)
    am = league_info.get("away_multiplier", AWAY_MULTIPLIER)
    league_avg = league_info.get("avg_goals_per_match", MODEL.get("varsayilan_lig_gol_ort", 2.7))
    team_avg = league_avg / 2.0

    # check if xg data is available
    home_xg_ok = all(k in home_stats for k in ("xg_per_match", "xga_per_match"))
    away_xg_ok = all(k in away_stats for k in ("xg_per_match", "xga_per_match"))
    
    # fallback keys for old data format
    if not home_xg_ok:
        home_xg_ok = all(k in home_stats for k in ("mac_basi_beklenen_gol_xg", "mac_basi_beklenen_yenilen_gol_xga"))
    if not away_xg_ok:
        away_xg_ok = all(k in away_stats for k in ("mac_basi_beklenen_gol_xg", "mac_basi_beklenen_yenilen_gol_xga"))
    
    if home_xg_ok and away_xg_ok:
        home_attack = _shrink(home_stats, "xg_per_match", team_avg) or _shrink(home_stats, "mac_basi_beklenen_gol_xg", team_avg)
        away_defense = _shrink(away_stats, "xga_per_match", team_avg) or _shrink(away_stats, "mac_basi_beklenen_yenilen_gol_xga", team_avg)
        away_attack = _shrink(away_stats, "xg_per_match", team_avg) or _shrink(away_stats, "mac_basi_beklenen_gol_xg", team_avg)
        home_defense = _shrink(home_stats, "xga_per_match", team_avg) or _shrink(home_stats, "mac_basi_beklenen_yenilen_gol_xga", team_avg)
    else:
        home_attack = _shrink(home_stats, "goals_scored_per_match", team_avg) or _shrink(home_stats, "mac_basi_atilan_gol", team_avg)
        away_defense = _shrink(away_stats, "goals_conceded_per_match", team_avg) or _shrink(away_stats, "mac_basi_yenilen_gol", team_avg)
        away_attack = _shrink(away_stats, "goals_scored_per_match", team_avg) or _shrink(away_stats, "mac_basi_atilan_gol", team_avg)
        home_defense = _shrink(home_stats, "goals_conceded_per_match", team_avg) or _shrink(home_stats, "mac_basi_yenilen_gol", team_avg)
        
    if None in (home_attack, away_defense, away_attack, home_defense):
        home_attack = _shrink(home_stats, "goals_scored_per_match", team_avg) or _shrink(home_stats, "mac_basi_atilan_gol", team_avg)
        away_defense = _shrink(away_stats, "goals_conceded_per_match", team_avg) or _shrink(away_stats, "mac_basi_yenilen_gol", team_avg)
        away_attack = _shrink(away_stats, "goals_scored_per_match", team_avg) or _shrink(away_stats, "mac_basi_atilan_gol", team_avg)
        home_defense = _shrink(home_stats, "goals_conceded_per_match", team_avg) or _shrink(home_stats, "mac_basi_yenilen_gol", team_avg)

    if None in (home_attack, away_defense, away_attack, home_defense):
        return None, None
    
    home_attack_strength = home_attack / team_avg if team_avg > 0 else 1.0
    away_defense_weakness = away_defense / team_avg if team_avg > 0 else 1.0
    
    away_attack_strength = away_attack / team_avg if team_avg > 0 else 1.0
    home_defense_weakness = home_defense / team_avg if team_avg > 0 else 1.0
    
    home_goals = home_attack_strength * away_defense_weakness * team_avg * ha
    away_goals = away_attack_strength * home_defense_weakness * team_avg * am

    return round(home_goals, 2), round(away_goals, 2)

def calc_poisson_probs(home_exp, away_exp, rho=0.0):
    # calculate match outcome probabilities from expected goals
    if not home_exp or not away_exp:
        return None

    def dixon_coles_tau(x, y, l_x, l_y, r):
        if r == 0:
            return 1.0
        if x == 0 and y == 0:
            return 1 - l_x * l_y * r
        elif x == 0 and y == 1:
            return 1 + l_x * r
        elif x == 1 and y == 0:
            return 1 + l_y * r
        elif x == 1 and y == 1:
            return 1 - r
        return 1.0

    home_win = draw = away_win = 0.0
    over_25 = btts_yes = 0.0
    score_probs = []

    for i in range(MAX_GOALS + 1):
        p_h = _poisson_pmf(i, home_exp)
        for j in range(MAX_GOALS + 1):
            p_a = _poisson_pmf(j, away_exp)
            tau = max(0.0, dixon_coles_tau(i, j, home_exp, away_exp, rho))
            p = p_h * p_a * tau

            if i > j:
                home_win += p
            elif i == j:
                draw += p
            else:
                away_win += p

            if i + j > 2.5:
                over_25 += p
            if i >= 1 and j >= 1:
                btts_yes += p

            score_probs.append((f"{i}-{j}", p))

    total = home_win + draw + away_win
    if total <= 0:
        return None

    home_win, draw, away_win = (x / total for x in (home_win, draw, away_win))
    score_probs.sort(key=lambda x: x[1], reverse=True)

    return {
        "home_win_pct": round(100 * home_win, 1),
        "draw_pct": round(100 * draw, 1),
        "away_win_pct": round(100 * away_win, 1),
        "over_2_5_pct": round(100 * over_25 / total, 1),
        "under_2_5_pct": round(100 * (1 - over_25 / total), 1),
        "btts_yes_pct": round(100 * btts_yes / total, 1),
        "btts_no_pct": round(100 * (1 - btts_yes / total), 1),
        "most_likely_scores": [
            {"score": s, "prob_pct": round(100 * p / total, 1)}
            for s, p in score_probs[:10]
        ],
        "most_likely_margin_score": next(
            (
                {"score": s, "prob_pct": round(100 * p / total, 1)}
                for s, p in score_probs
                if abs(int(s.split("-")[0]) - int(s.split("-")[1])) >= 2
            ),
            None,
        ),
        "expected_total_goals": round(home_exp + away_exp, 2),
    }

def calc_card_expectation(home_stats, away_stats, referee_info):
    # calculate expected cards from team + referee data
    team_based = None
    
    league_yellow_avg = 2.0
    if home_stats and away_stats:
        home_cards = _blend(
            _shrink(home_stats, "yellows_per_match", league_yellow_avg) or _shrink(home_stats, "mac_basi_sari_kart", league_yellow_avg),
            _shrink(away_stats, "yellows_against_per_match", league_yellow_avg) or _shrink(away_stats, "mac_basi_rakip_sari_kart", league_yellow_avg)
        )
        away_cards = _blend(
            _shrink(away_stats, "yellows_per_match", league_yellow_avg) or _shrink(away_stats, "mac_basi_sari_kart", league_yellow_avg),
            _shrink(home_stats, "yellows_against_per_match", league_yellow_avg) or _shrink(home_stats, "mac_basi_rakip_sari_kart", league_yellow_avg)
        )
                             
        if away_cards is not None:
            away_cards *= MODEL.get("deplasman_kart_carpani", 1.06)
            
        if home_cards is not None and away_cards is not None:
            team_based = home_cards + away_cards

    ref_based = None
    if referee_info:
        ref_based = referee_info.get("yellows_per_match") or referee_info.get("mac_basi_sari")

    if team_based is None and ref_based is None:
        return None

    if team_based is None:
        final = ref_based
        method = "referee average only (no team data)"
    elif ref_based is None:
        final = team_based
        method = "team average only (no referee data)"
    else:
        final = (1 - REFEREE_WEIGHT) * team_based + REFEREE_WEIGHT * ref_based
        method = f"team ({team_based:.1f}) + referee ({ref_based:.1f}) blend"

    played_matches = min(home_stats.get("played_matches", 10), away_stats.get("played_matches", 10)) if home_stats and away_stats else None
    dispersion = MODEL.get("kart_dispersion", 1.15)
    low, high = _confidence_interval(final, dispersion=dispersion, played_matches=played_matches)
    
    result = {
        "expected_yellows": round(final, 1),
        "low_bound": low,
        "high_bound": high,
        "method": method,
    }

    ref_reds = None
    if referee_info:
        ref_reds = referee_info.get("reds_per_match") or referee_info.get("mac_basi_kirmizi")
    team_reds = None
    league_red_avg = 0.15
    if home_stats and away_stats:
        h_r = _blend(_shrink(home_stats, "reds_per_match", league_red_avg),
                     _shrink(away_stats, "reds_against_per_match", league_red_avg))
        a_r = _blend(_shrink(away_stats, "reds_per_match", league_red_avg),
                      _shrink(home_stats, "reds_against_per_match", league_red_avg))
        if a_r is not None:
            a_r *= MODEL.get("deplasman_kart_carpani", 1.06)
        if h_r is not None and a_r is not None:
            team_reds = h_r + a_r
            
    red_lambda = None
    if team_reds is not None and ref_reds is not None:
        red_lambda = (1 - REFEREE_WEIGHT) * team_reds + REFEREE_WEIGHT * ref_reds
    elif ref_reds is not None:
        red_lambda = ref_reds
    elif team_reds is not None:
        red_lambda = team_reds
        
    if red_lambda is not None:
        result["red_card_prob_pct"] = round(100 * (1 - _poisson_pmf(0, red_lambda)), 1)

    return result

def _simple_expectation(home_stats, away_stats, own_key, opp_key, decimals=1, home_mult=1.0, away_mult=1.0, league_avg=4.5, dispersion=1.0):
    # calculate symmetric expectations (corners, offsides etc)
    if not home_stats or not away_stats:
        return None
    home = _blend(_shrink(home_stats, own_key, league_avg), _shrink(away_stats, opp_key, league_avg))
    away = _blend(_shrink(away_stats, own_key, league_avg), _shrink(home_stats, opp_key, league_avg))
    
    if home is None or away is None:
        return None
        
    home *= home_mult
    away *= away_mult
    total = home + away
    
    played_matches = min(home_stats.get("played_matches", 10), away_stats.get("played_matches", 10))
    low, high = _confidence_interval(total, dispersion=dispersion, played_matches=played_matches)
    
    return {
        "home_expected": round(home, decimals),
        "away_expected": round(away, decimals),
        "total_expected": round(total, decimals),
        "low_bound": low,
        "high_bound": high,
    }

def calc_corners(home_stats, away_stats):
    return _simple_expectation(
        home_stats, away_stats,
        "corners_per_match", "corners_against_per_match",
        home_mult=MODEL.get("korner_ev_carpani", 1.05),
        away_mult=MODEL.get("korner_dep_carpani", 0.95),
        league_avg=4.5,
        dispersion=MODEL.get("korner_dispersion", 1.20)
    ) or _simple_expectation(
        home_stats, away_stats,
        "mac_basi_korner", "mac_basi_rakip_korner",
        home_mult=MODEL.get("korner_ev_carpani", 1.05),
        away_mult=MODEL.get("korner_dep_carpani", 0.95),
        league_avg=4.5,
        dispersion=MODEL.get("korner_dispersion", 1.20)
    )

def calc_offsides(home_stats, away_stats):
    return _simple_expectation(
        home_stats, away_stats,
        "offsides_per_match", "offsides_against_per_match", league_avg=1.8
    ) or _simple_expectation(
        home_stats, away_stats,
        "mac_basi_ofsayt", "mac_basi_rakip_ofsayt", league_avg=1.8
    )

def calc_fouls(home_stats, away_stats):
    # fouls calculation
    if not home_stats or not away_stats:
        return None
        
    league_avg = 12.0
    home = _shrink(home_stats, "fouls_per_match", league_avg) or _shrink(home_stats, "mac_basi_faul", league_avg)
    away = _shrink(away_stats, "fouls_per_match", league_avg) or _shrink(away_stats, "mac_basi_faul", league_avg)
    
    if not isinstance(home, (int, float)) or not isinstance(away, (int, float)):
        return None
        
    home *= 0.95
    away *= 1.05
    total = home + away
    
    played_matches = min(home_stats.get("played_matches", 10), away_stats.get("played_matches", 10))
    low, high = _confidence_interval(total, dispersion=MODEL.get("faul_dispersion", 1.10), played_matches=played_matches)
    return {
        "home_expected": round(home, 1),
        "away_expected": round(away, 1),
        "total_expected": round(total, 1),
        "low_bound": low,
        "high_bound": high,
    }

def calc_penalty_prob(home_stats, away_stats):
    # penalty probability from team records
    if not home_stats or not away_stats:
        return None

    def rate(stats, key):
        total = stats.get(key)
        games = stats.get("played_matches")
        if isinstance(total, (int, float)) and games:
            return total / games
        return None

    components = [
        rate(home_stats, "penalties_won") or rate(home_stats, "toplam_kazanilan_penalti"),
        rate(away_stats, "penalties_conceded") or rate(away_stats, "toplam_verilen_penalti"),
        rate(away_stats, "penalties_won") or rate(away_stats, "toplam_kazanilan_penalti"),
        rate(home_stats, "penalties_conceded") or rate(home_stats, "toplam_verilen_penalti"),
    ]
    valid = [c for c in components if c is not None]
    if not valid:
        return None

    expected = sum(valid) / 2 if len(valid) >= 2 else valid[0]
    prob = 1 - math.exp(-expected) if expected > 0 else 0.0
    return {
        "expected_penalties_per_match": round(expected, 2),
        "at_least_one_penalty_pct": round(100 * prob, 1),
    }

def generate_base_prediction(home_stats, away_stats, referee_info, league_id=None):
    # generate full statistical base prediction
    base = {}

    home_goals, away_goals = calc_expected_goals(home_stats, away_stats, league_id)
    if home_goals and away_goals:
        base["expected_goals"] = {
            "home": home_goals,
            "away": away_goals,
            "total": round(home_goals + away_goals, 2),
        }
        league_info = {}
        if league_id:
            for l in CONFIG.get("leagues", []):
                if l.get("id") == league_id:
                    league_info = l
                    break
        rho = league_info.get("dixon_coles_rho", MODEL.get("dixon_coles_rho", -0.13))
        poisson = calc_poisson_probs(home_goals, away_goals, rho)
        if poisson:
            base["poisson_probabilities"] = poisson

    for name, value in [
        ("cards", calc_card_expectation(home_stats, away_stats, referee_info)),
        ("corners", calc_corners(home_stats, away_stats)),
        ("offsides", calc_offsides(home_stats, away_stats)),
        ("fouls", calc_fouls(home_stats, away_stats)),
        ("penalty", calc_penalty_prob(home_stats, away_stats)),
    ]:
        if value:
            base[name] = value

    return base
