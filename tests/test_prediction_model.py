import pytest
import math
from shared.prediction_model import (
    _shrink,
    _blend,
    _poisson_pmf,
    _poisson_cdf,
    calc_expected_goals,
    calc_poisson_probs,
)

def test_poisson_pmf():
    # P(X=0) for lambda=0 should be 1.0
    assert _poisson_pmf(0, 0) == 1.0
    # P(X=1) for lambda=0 should be 0.0
    assert _poisson_pmf(1, 0) == 0.0
    
    # Check regular poisson for lambda = 2.0, k = 1
    # formula: (2^1 * e^-2) / 1!
    expected = 2.0 * math.exp(-2.0)
    assert math.isclose(_poisson_pmf(1, 2.0), expected)

def test_poisson_cdf():
    # CDF for lambda 2, k=1 is PMF(0, 2) + PMF(1, 2)
    expected = _poisson_pmf(0, 2.0) + _poisson_pmf(1, 2.0)
    assert math.isclose(_poisson_cdf(1, 2.0), expected)

def test_shrink():
    # Test empirical bayes shrinkage
    stats = {"xg_per_match": 2.0, "played_matches": 10}
    league_avg = 1.0
    # k = 8 (default)
    # val = (10 * 2.0 + 8 * 1.0) / (10 + 8) = (20 + 8) / 18 = 28 / 18 = 1.5555...
    result = _shrink(stats, "xg_per_match", league_avg, k=8)
    assert math.isclose(result, 28 / 18)
    
    # Missing key
    assert _shrink(stats, "missing", league_avg) is None

def test_blend():
    assert _blend(2.0, 4.0) == 3.0
    assert _blend(2.0, None) == 2.0
    assert _blend(None, None) is None

def test_calc_expected_goals(monkeypatch):
    home_stats = {
        "xg_per_match": 1.8,
        "xga_per_match": 1.2,
        "played_matches": 10
    }
    away_stats = {
        "xg_per_match": 1.5,
        "xga_per_match": 1.4,
        "played_matches": 10
    }
    
    # Mock CONFIG so we don't depend on actual config.json
    mock_config = {
        "model_parametreleri": {
            "ev_sahibi_avantaji": 1.1,
            "deplasman_carpani": 0.9,
            "varsayilan_lig_gol_ort": 2.5
        },
        "leagues": []
    }
    monkeypatch.setattr("shared.prediction_model.CONFIG", mock_config)
    monkeypatch.setattr("shared.prediction_model.HOME_ADVANTAGE", 1.1)
    monkeypatch.setattr("shared.prediction_model.AWAY_MULTIPLIER", 0.9)
    
    home_goals, away_goals = calc_expected_goals(home_stats, away_stats)
    
    assert home_goals is not None
    assert away_goals is not None
    assert isinstance(home_goals, float)
    assert isinstance(away_goals, float)

def test_calc_poisson_probs():
    probs = calc_poisson_probs(1.5, 1.2, rho=0.0)
    
    assert probs is not None
    assert "home_win_pct" in probs
    assert "draw_pct" in probs
    assert "away_win_pct" in probs
    
    # Total percentage should be close to 100
    total = probs["home_win_pct"] + probs["draw_pct"] + probs["away_win_pct"]
    assert math.isclose(total, 100.0, abs_tol=0.2)
