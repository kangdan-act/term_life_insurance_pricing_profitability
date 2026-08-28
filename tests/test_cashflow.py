from pathlib import Path

import pytest

from life_pricing.cashflow import (
    CashFlowError,
    build_policy_cash_flows,
    summarize_policy,
    year_expenses,
)
from life_pricing.config import load_assumptions
from life_pricing.mortality import mortality_curve_for_policy
from life_pricing.projection import project_policy

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "assumptions.yaml"


@pytest.fixture
def assumptions():
    return load_assumptions(CONFIG_PATH)


@pytest.fixture
def projection(assumptions):
    qx = mortality_curve_for_policy(
        assumptions, issue_age=40, sex="male", smoker_status="nonsmoker",
        underwriting_class="Standard", face_amount=300_000,
    )
    return project_policy(assumptions, issue_age=40, mortality_rates_qx=qx, face_amount=300_000)


def test_year_one_has_acquisition_expense_and_acquisition_pct(assumptions):
    acq, maint, prem_related = year_expenses(assumptions, 1, beginning_inforce=1.0, expected_premium=1000.0)
    assert acq == pytest.approx(assumptions.acquisition_fixed_expense)
    assert maint == pytest.approx(assumptions.maintenance_per_inforce_year)
    assert prem_related == pytest.approx(assumptions.acquisition_pct_first_year_premium * 1000.0)


def test_later_years_have_no_acquisition_expense_and_use_renewal_pct(assumptions):
    acq, maint, prem_related = year_expenses(assumptions, 5, beginning_inforce=0.8, expected_premium=800.0)
    assert acq == 0.0
    assert maint == pytest.approx(assumptions.maintenance_per_inforce_year * 0.8)
    assert prem_related == pytest.approx(assumptions.renewal_pct_premium * 800.0)


def test_negative_premium_rejected(assumptions, projection):
    with pytest.raises(CashFlowError):
        build_policy_cash_flows(assumptions, projection, annual_premium=-1.0)


def test_empty_projection_rejected_by_cashflow_builder(assumptions):
    with pytest.raises(CashFlowError):
        build_policy_cash_flows(assumptions, [], annual_premium=1000.0)


def test_present_value_identity_holds_every_year(assumptions, projection):
    cash_flows = build_policy_cash_flows(assumptions, projection, annual_premium=1500.0)
    for r in cash_flows:
        assert r.present_value_net_cash_flow == pytest.approx(r.discount_factor * r.net_cash_flow)


def test_zero_premium_leaves_only_claims_and_expenses(assumptions, projection):
    cash_flows = build_policy_cash_flows(assumptions, projection, annual_premium=0.0)
    for r in cash_flows:
        assert r.expected_premium == pytest.approx(0.0)
        assert r.premium_related_expense == pytest.approx(0.0)
        expected_net = -(r.expected_death_benefit + r.acquisition_expense + r.maintenance_expense)
        assert r.net_cash_flow == pytest.approx(expected_net)


def test_summarize_policy_pv_identity(assumptions, projection):
    cash_flows = build_policy_cash_flows(assumptions, projection, annual_premium=1500.0)
    summary = summarize_policy(cash_flows)
    assert summary.pv_profit == pytest.approx(
        summary.pv_premiums - summary.pv_claims - summary.pv_expenses, rel=1e-9
    )


def test_summarize_policy_rejects_empty_input():
    with pytest.raises(CashFlowError):
        summarize_policy([])
