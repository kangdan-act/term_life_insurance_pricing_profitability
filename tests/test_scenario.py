from copy import deepcopy
from pathlib import Path

import pytest

from life_pricing.config import load_assumptions
from life_pricing.scenario import (
    INTEREST_RATE_SCENARIOS,
    LAPSE_STRESS_SCENARIOS,
    MORTALITY_STRESS_SCENARIOS,
    PROFIT_MARGIN_SCENARIOS,
    apply_scenario,
    run_full_sensitivity_grid,
    run_interest_rate_sensitivity,
    run_lapse_stress_sensitivity,
    run_mortality_stress_sensitivity,
    run_profit_margin_sensitivity,
)

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "assumptions.yaml"

POLICY_KWARGS = dict(issue_age=40, sex="male", smoker_status="nonsmoker", underwriting_class="Standard", face_amount=300_000)


@pytest.fixture
def assumptions():
    return load_assumptions(CONFIG_PATH)


def test_apply_scenario_does_not_mutate_base_assumptions(assumptions):
    base_raw_snapshot = deepcopy(assumptions.raw)
    apply_scenario(assumptions, lambda raw: raw["interest"].__setitem__("annual_effective_rate", 0.99))
    assert assumptions.raw == base_raw_snapshot


def test_interest_rate_sensitivity_matches_configured_grid(assumptions):
    result = run_interest_rate_sensitivity(assumptions, **POLICY_KWARGS)
    assert result["annual_effective_rate"].tolist() == INTEREST_RATE_SCENARIOS
    assert (result["annual_premium"] > 0).all()


def test_indicated_premium_decreases_as_rate_increases(assumptions):
    result = run_interest_rate_sensitivity(assumptions, **POLICY_KWARGS).sort_values("annual_effective_rate")
    premiums = result["annual_premium"].tolist()
    assert premiums == sorted(premiums, reverse=True)


def test_profit_margin_sensitivity_matches_configured_grid(assumptions):
    result = run_profit_margin_sensitivity(assumptions, **POLICY_KWARGS)
    assert result["target_profit_margin"].tolist() == PROFIT_MARGIN_SCENARIOS
    for _, row in result.iterrows():
        assert row["pv_profit_margin"] == pytest.approx(row["target_profit_margin"], abs=1e-6)


def test_indicated_premium_increases_with_target_margin(assumptions):
    result = run_profit_margin_sensitivity(assumptions, **POLICY_KWARGS).sort_values("target_profit_margin")
    premiums = result["annual_premium"].tolist()
    assert premiums == sorted(premiums)


def test_mortality_stress_sensitivity_matches_configured_grid(assumptions):
    result = run_mortality_stress_sensitivity(assumptions, **POLICY_KWARGS)
    assert result["mortality_stress_multiplier"].tolist() == MORTALITY_STRESS_SCENARIOS


def test_indicated_premium_increases_with_mortality_stress_grid(assumptions):
    result = run_mortality_stress_sensitivity(assumptions, **POLICY_KWARGS).sort_values("mortality_stress_multiplier")
    premiums = result["annual_premium"].tolist()
    assert premiums == sorted(premiums)


def test_lapse_stress_sensitivity_matches_configured_grid(assumptions):
    result = run_lapse_stress_sensitivity(assumptions, **POLICY_KWARGS)
    assert result["lapse_multiplier"].tolist() == LAPSE_STRESS_SCENARIOS


def test_scenario_runs_do_not_mutate_base_assumptions(assumptions):
    base_raw_snapshot = deepcopy(assumptions.raw)
    run_full_sensitivity_grid(assumptions, **POLICY_KWARGS)
    assert assumptions.raw == base_raw_snapshot


def test_full_sensitivity_grid_returns_all_four_tables(assumptions):
    grids = run_full_sensitivity_grid(assumptions, **POLICY_KWARGS)
    assert set(grids.keys()) == {"interest_rate", "profit_margin", "mortality_stress", "lapse_stress"}
    for df in grids.values():
        assert not df.empty
        assert (df["annual_premium"] > 0).all()


def test_custom_grid_values_are_honored(assumptions):
    custom_rates = [0.01, 0.10]
    result = run_interest_rate_sensitivity(assumptions, **POLICY_KWARGS, rates=custom_rates)
    assert result["annual_effective_rate"].tolist() == custom_rates
