from pathlib import Path

import pandas as pd
import pytest

from life_pricing.challenger import ChallengerModelError, ChallengerResult, fit_challenger
from life_pricing.config import load_assumptions
from life_pricing.experience import simulate_policy_exposures
from life_pricing.portfolio import generate_synthetic_portfolio

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "assumptions.yaml"


@pytest.fixture(scope="module")
def assumptions():
    return load_assumptions(CONFIG_PATH)


@pytest.fixture(scope="module")
def portfolio_and_exposures(assumptions):
    portfolio = generate_synthetic_portfolio(assumptions, n_policies=4000, random_seed=21)
    exposures = simulate_policy_exposures(assumptions, portfolio, random_seed=21)
    return portfolio, exposures


def test_death_challenger_returns_valid_result(portfolio_and_exposures):
    portfolio, exposures = portfolio_and_exposures
    result = fit_challenger(exposures, portfolio, outcome="death")

    assert isinstance(result, ChallengerResult)
    assert result.outcome == "death"
    assert "logit_expected" in result.feature_names
    assert result.baseline_log_loss > 0
    assert result.challenger_log_loss > 0
    assert result.n_observations > 0
    assert result.n_events > 0
    assert isinstance(result.challenger_beats_baseline_log_loss, bool)


def test_lapse_challenger_returns_valid_result(portfolio_and_exposures):
    portfolio, exposures = portfolio_and_exposures
    result = fit_challenger(exposures, portfolio, outcome="lapse")

    assert result.outcome == "lapse"
    assert result.baseline_log_loss > 0
    assert result.challenger_log_loss > 0


def test_baseline_is_informative_for_both_outcomes(portfolio_and_exposures):
    """The challenger's coefficient on the actuarial baseline's own
    logit(expected rate) should be positive -- i.e. the actuarial table is
    genuinely predictive, not something the statistical model ignores."""
    portfolio, exposures = portfolio_and_exposures
    for outcome in ("death", "lapse"):
        result = fit_challenger(exposures, portfolio, outcome=outcome)
        assert result.coefficients["logit_expected"] > 0


def test_custom_categorical_features(portfolio_and_exposures):
    portfolio, exposures = portfolio_and_exposures
    result = fit_challenger(exposures, portfolio, outcome="death", categorical_features=["distribution_channel"])
    assert any(name.startswith("distribution_channel") for name in result.feature_names)
    assert not any(name.startswith("sex") for name in result.feature_names)


def test_invalid_outcome_raises(portfolio_and_exposures):
    portfolio, exposures = portfolio_and_exposures
    with pytest.raises(ChallengerModelError):
        fit_challenger(exposures, portfolio, outcome="not_a_real_outcome")


def test_empty_exposures_raises(portfolio_and_exposures):
    portfolio, _ = portfolio_and_exposures
    from life_pricing.experience import EXPOSURE_COLUMNS

    empty = pd.DataFrame(columns=EXPOSURE_COLUMNS)
    with pytest.raises(ChallengerModelError):
        fit_challenger(empty, portfolio, outcome="death")


def test_no_variation_in_outcome_raises(portfolio_and_exposures):
    portfolio, exposures = portfolio_and_exposures
    no_events = exposures.copy()
    no_events["actual_death"] = 0
    no_events["actual_lapse"] = 0
    with pytest.raises(ChallengerModelError):
        fit_challenger(no_events, portfolio, outcome="death")
