from copy import deepcopy
from pathlib import Path

import pytest

from life_pricing.cashflow import build_policy_cash_flows, summarize_policy
from life_pricing.config import ProjectAssumptions, load_assumptions
from life_pricing.mortality import mortality_curve_for_policy
from life_pricing.premium import PremiumSolveError, solve_annual_premium, solve_break_even_premium
from life_pricing.projection import project_policy

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "assumptions.yaml"

ISSUE_AGE = 40
SEX = "male"
SMOKER_STATUS = "nonsmoker"
UW_CLASS = "Standard"
FACE_AMOUNT = 300_000


@pytest.fixture
def assumptions():
    return load_assumptions(CONFIG_PATH)


def _projection_for(assumptions, issue_age=ISSUE_AGE, sex=SEX, smoker_status=SMOKER_STATUS, uw_class=UW_CLASS, face_amount=FACE_AMOUNT):
    qx = mortality_curve_for_policy(
        assumptions, issue_age=issue_age, sex=sex, smoker_status=smoker_status,
        underwriting_class=uw_class, face_amount=face_amount,
    )
    return project_policy(assumptions, issue_age=issue_age, mortality_rates_qx=qx, face_amount=face_amount)


def _with_raw_override(assumptions, mutate_fn):
    raw = deepcopy(assumptions.raw)
    mutate_fn(raw)
    return ProjectAssumptions(raw=raw)


def test_break_even_premium_gives_zero_pv_profit(assumptions):
    projection = _projection_for(assumptions)
    premium = solve_break_even_premium(assumptions, projection)
    cash_flows = build_policy_cash_flows(assumptions, projection, premium)
    summary = summarize_policy(cash_flows)
    assert summary.pv_profit == pytest.approx(0.0, abs=1e-6)
    assert summary.pv_profit_margin == pytest.approx(0.0, abs=1e-6)


@pytest.mark.parametrize("target_margin", [0.0, 0.05, 0.10, 0.15])
def test_target_premium_reproduces_target_margin(assumptions, target_margin):
    projection = _projection_for(assumptions)
    premium = solve_annual_premium(assumptions, projection, target_margin=target_margin)
    cash_flows = build_policy_cash_flows(assumptions, projection, premium)
    summary = summarize_policy(cash_flows)
    assert summary.pv_profit_margin == pytest.approx(target_margin, abs=1e-6)


def test_default_target_margin_comes_from_assumptions(assumptions):
    projection = _projection_for(assumptions)
    premium = solve_annual_premium(assumptions, projection)
    cash_flows = build_policy_cash_flows(assumptions, projection, premium)
    summary = summarize_policy(cash_flows)
    assert summary.pv_profit_margin == pytest.approx(assumptions.target_profit_margin, abs=1e-6)


def test_premium_is_positive(assumptions):
    projection = _projection_for(assumptions)
    assert solve_annual_premium(assumptions, projection) > 0


def test_indicated_premium_increases_with_mortality_stress(assumptions):
    base_projection = _projection_for(assumptions)
    base_premium = solve_annual_premium(assumptions, base_projection)

    stressed = _with_raw_override(assumptions, lambda raw: raw["mortality"].__setitem__("stress_multiplier", 2.0))
    stressed_projection = _projection_for(stressed)
    stressed_premium = solve_annual_premium(stressed, stressed_projection)

    assert stressed_premium > base_premium


def test_indicated_premium_increases_monotonically_with_mortality_stress(assumptions):
    premiums = []
    for mult in [1.0, 2.0, 5.0, 10.0]:
        stressed = _with_raw_override(assumptions, lambda raw, m=mult: raw["mortality"].__setitem__("stress_multiplier", m))
        stressed_projection = _projection_for(stressed)
        premiums.append(solve_annual_premium(stressed, stressed_projection))

    assert premiums == sorted(premiums)
    assert premiums[0] < premiums[-1]


def test_indicated_premium_increases_with_expenses(assumptions):
    base_projection = _projection_for(assumptions)
    base_premium = solve_annual_premium(assumptions, base_projection)

    higher_expense = _with_raw_override(
        assumptions,
        lambda raw: raw["expenses"].__setitem__(
            "maintenance_per_inforce_year", raw["expenses"]["maintenance_per_inforce_year"] * 5
        ),
    )
    higher_expense_premium = solve_annual_premium(higher_expense, base_projection)

    assert higher_expense_premium > base_premium


def test_indicated_premium_decreases_as_discount_rate_increases(assumptions):
    base_projection = _projection_for(assumptions)
    base_premium = solve_annual_premium(assumptions, base_projection)

    higher_rate = _with_raw_override(
        assumptions,
        lambda raw: raw["interest"].__setitem__(
            "annual_effective_rate", raw["interest"]["annual_effective_rate"] + 0.02
        ),
    )
    # Decrements (in-force/death/lapse) don't depend on interest, but the
    # discount_factor column does -- the projection must be rebuilt.
    higher_rate_projection = _projection_for(higher_rate)
    higher_rate_premium = solve_annual_premium(higher_rate, higher_rate_projection)

    assert higher_rate_premium < base_premium


def test_no_negative_premiums_across_edge_grid(assumptions):
    for issue_age in (25, 60):
        for sex, smoker_status in (("male", "nonsmoker"), ("female", "smoker")):
            for uw_class in assumptions.underwriting_classes:
                for face_amount in (assumptions.face_amount_min, assumptions.face_amount_max):
                    projection = _projection_for(
                        assumptions,
                        issue_age=issue_age,
                        sex=sex,
                        smoker_status=smoker_status,
                        uw_class=uw_class,
                        face_amount=face_amount,
                    )
                    premium = solve_annual_premium(assumptions, projection)
                    assert premium > 0


def test_invalid_target_margin_raises(assumptions):
    projection = _projection_for(assumptions)
    with pytest.raises(PremiumSolveError):
        solve_annual_premium(assumptions, projection, target_margin=1.0)
    with pytest.raises(PremiumSolveError):
        solve_annual_premium(assumptions, projection, target_margin=-0.1)


def test_empty_projection_raises(assumptions):
    with pytest.raises(PremiumSolveError):
        solve_annual_premium(assumptions, [])
