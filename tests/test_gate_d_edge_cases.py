"""TEST_SPEC.md Gate D -- edge cases, run through the full pipeline:
mortality -> projection -> premium solve -> cash flow -> summary.
"""

from copy import deepcopy
from pathlib import Path

import pytest

from life_pricing.cashflow import build_policy_cash_flows, summarize_policy
from life_pricing.config import ProjectAssumptions, load_assumptions
from life_pricing.mortality import mortality_curve_for_policy
from life_pricing.premium import solve_annual_premium
from life_pricing.projection import project_policy

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "assumptions.yaml"

SEX_SMOKER_COMBOS = [
    ("male", "nonsmoker"),
    ("female", "nonsmoker"),
    ("male", "smoker"),
    ("female", "smoker"),
]


@pytest.fixture
def assumptions():
    return load_assumptions(CONFIG_PATH)


def _run_full_pipeline(assumptions, issue_age, sex, smoker_status, uw_class, face_amount):
    qx = mortality_curve_for_policy(
        assumptions, issue_age=issue_age, sex=sex, smoker_status=smoker_status,
        underwriting_class=uw_class, face_amount=face_amount,
    )
    projection = project_policy(assumptions, issue_age=issue_age, mortality_rates_qx=qx, face_amount=face_amount)
    premium = solve_annual_premium(assumptions, projection)
    cash_flows = build_policy_cash_flows(assumptions, projection, premium)
    summary = summarize_policy(cash_flows)
    return projection, premium, cash_flows, summary


@pytest.mark.parametrize("issue_age", [25, 60])
@pytest.mark.parametrize("sex,smoker_status", SEX_SMOKER_COMBOS)
@pytest.mark.parametrize("uw_class", ["Preferred Plus", "Preferred", "Standard"])
@pytest.mark.parametrize("face_amount_bound", ["min", "max"])
def test_full_grid_runs_and_reproduces_target_margin(
    assumptions, issue_age, sex, smoker_status, uw_class, face_amount_bound
):
    face_amount = assumptions.face_amount_min if face_amount_bound == "min" else assumptions.face_amount_max

    _, premium, _, summary = _run_full_pipeline(
        assumptions, issue_age, sex, smoker_status, uw_class, face_amount
    )

    assert premium > 0
    assert summary.pv_profit_margin == pytest.approx(assumptions.target_profit_margin, abs=1e-6)


def test_zero_lapse_scenario_runs_end_to_end(assumptions):
    raw = deepcopy(assumptions.raw)
    raw["lapse"]["by_duration"] = {k: 0.0 for k in raw["lapse"]["by_duration"]}
    zero_lapse = ProjectAssumptions(raw=raw)

    projection, premium, _, summary = _run_full_pipeline(
        zero_lapse, 40, "male", "nonsmoker", "Standard", 300_000
    )

    assert premium > 0
    assert summary.pv_profit_margin == pytest.approx(zero_lapse.target_profit_margin, abs=1e-6)
    # with no lapse, the only decrement is mortality, so in-force declines
    # strictly more slowly than the base (nonzero-lapse) scenario.
    base_projection = project_policy(
        assumptions,
        issue_age=40,
        mortality_rates_qx=mortality_curve_for_policy(
            assumptions, issue_age=40, sex="male", smoker_status="nonsmoker",
            underwriting_class="Standard", face_amount=300_000,
        ),
        face_amount=300_000,
    )
    assert projection[-1].ending_inforce_probability > base_projection[-1].ending_inforce_probability


def test_zero_expense_scenario_runs_end_to_end(assumptions):
    raw = deepcopy(assumptions.raw)
    for key in raw["expenses"]:
        raw["expenses"][key] = 0.0
    zero_expense = ProjectAssumptions(raw=raw)

    projection, premium, cash_flows, summary = _run_full_pipeline(
        zero_expense, 40, "male", "nonsmoker", "Standard", 300_000
    )

    assert premium > 0
    for r in cash_flows:
        assert r.acquisition_expense == 0.0
        assert r.maintenance_expense == 0.0
        assert r.premium_related_expense == 0.0
    assert summary.pv_expenses == pytest.approx(0.0)
    assert summary.pv_profit_margin == pytest.approx(zero_expense.target_profit_margin, abs=1e-6)


def test_zero_interest_scenario_runs_end_to_end(assumptions):
    raw = deepcopy(assumptions.raw)
    raw["interest"]["annual_effective_rate"] = 0.0
    zero_interest = ProjectAssumptions(raw=raw)

    projection, premium, _, summary = _run_full_pipeline(
        zero_interest, 40, "male", "nonsmoker", "Standard", 300_000
    )

    assert premium > 0
    assert all(r.discount_factor == pytest.approx(1.0) for r in projection)
    assert summary.pv_profit_margin == pytest.approx(zero_interest.target_profit_margin, abs=1e-6)


@pytest.mark.parametrize("stress_multiplier", [2.0, 5.0, 10.0])
def test_high_mortality_stress_scenarios_stay_valid(assumptions, stress_multiplier):
    raw = deepcopy(assumptions.raw)
    raw["mortality"]["stress_multiplier"] = stress_multiplier
    stressed = ProjectAssumptions(raw=raw)

    projection, premium, cash_flows, summary = _run_full_pipeline(
        stressed, 40, "male", "nonsmoker", "Standard", 300_000
    )

    assert premium > 0
    for r in projection:
        assert 0.0 <= r.mortality_rate_qx <= 1.0
        assert 0.0 <= r.death_probability <= 1.0
    assert summary.pv_profit_margin == pytest.approx(stressed.target_profit_margin, abs=1e-6)
