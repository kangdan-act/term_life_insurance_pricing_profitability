"""Tests for portfolio_pricing.py (PROJECT_SPEC.md section 6).

Covers: full-portfolio indicated-premium solve, rate-cell book-premium
derivation, the combined per-policy pricing table, the segment rollup (with
and without A/E), and the error paths.
"""

from pathlib import Path

import numpy as np
import pytest

from life_pricing.config import load_assumptions
from life_pricing.experience import simulate_policy_exposures
from life_pricing.portfolio import generate_synthetic_portfolio
from life_pricing.portfolio_pricing import (
    PRICED_POLICY_COLUMNS,
    RATE_CELL_COLUMNS,
    SEGMENT_COLUMNS,
    PortfolioPricingError,
    build_rate_table,
    evaluate_portfolio_pricing,
    portfolio_profitability_by_segment,
    price_all_policies,
)
from life_pricing.premium import solve_annual_premium
from life_pricing.mortality import mortality_curve_for_policy
from life_pricing.projection import project_policy

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "assumptions.yaml"


@pytest.fixture
def assumptions():
    return load_assumptions(CONFIG_PATH)


@pytest.fixture
def small_portfolio(assumptions):
    return generate_synthetic_portfolio(assumptions, n_policies=250, random_seed=101)


def test_price_all_policies_preserves_row_count_and_adds_indicated_premium(assumptions, small_portfolio):
    priced = price_all_policies(assumptions, small_portfolio)
    assert len(priced) == len(small_portfolio)
    assert "indicated_premium" in priced.columns
    assert (priced["indicated_premium"] > 0).all()


def test_price_all_policies_matches_single_policy_solve(assumptions, small_portfolio):
    priced = price_all_policies(assumptions, small_portfolio)
    row = priced.iloc[0]
    qx = mortality_curve_for_policy(
        assumptions,
        issue_age=row.issue_age,
        sex=row.sex,
        smoker_status=row.smoker_status,
        underwriting_class=row.underwriting_class,
        face_amount=row.face_amount,
    )
    projection = project_policy(
        assumptions, issue_age=row.issue_age, mortality_rates_qx=qx, face_amount=row.face_amount
    )
    expected_premium = solve_annual_premium(assumptions, projection)
    assert row.indicated_premium == pytest.approx(expected_premium, rel=1e-9)


def test_price_all_policies_is_deterministic_for_fixed_seed(assumptions, small_portfolio):
    a = price_all_policies(assumptions, small_portfolio)
    b = price_all_policies(assumptions, small_portfolio)
    assert np.allclose(a["indicated_premium"], b["indicated_premium"])


def test_price_all_policies_rejects_empty_portfolio(assumptions, small_portfolio):
    with pytest.raises(PortfolioPricingError):
        price_all_policies(assumptions, small_portfolio.iloc[0:0])


def test_build_rate_table_schema_and_positive_premiums(assumptions, small_portfolio):
    priced = price_all_policies(assumptions, small_portfolio)
    rate_table = build_rate_table(assumptions, priced)
    for column in RATE_CELL_COLUMNS + ["book_premium", "cell_policy_count"]:
        assert column in rate_table.columns
    assert (rate_table["book_premium"] > 0).all()
    assert rate_table["cell_policy_count"].sum() == len(small_portfolio)


def test_evaluate_portfolio_pricing_schema(assumptions, small_portfolio):
    priced = evaluate_portfolio_pricing(assumptions, small_portfolio)
    assert list(priced.columns) == PRICED_POLICY_COLUMNS
    assert len(priced) == len(small_portfolio)
    assert (priced["book_premium"] > 0).all()


def test_indicated_pv_profit_margin_hits_target_by_construction(assumptions, small_portfolio):
    priced = evaluate_portfolio_pricing(assumptions, small_portfolio)
    assert np.allclose(
        priced["indicated_pv_profit_margin"], assumptions.target_profit_margin, atol=1e-6
    )


def test_book_premium_creates_realized_margin_dispersion(assumptions, small_portfolio):
    # Book premium is a coarser, cell-averaged rate, so realized pv_profit_margin
    # should NOT collapse to the target margin for every policy the way the
    # indicated (fully individualized) premium does.
    priced = evaluate_portfolio_pricing(assumptions, small_portfolio)
    assert priced["pv_profit_margin"].std() > 1e-6
    assert not np.allclose(priced["pv_profit_margin"], assumptions.target_profit_margin, atol=1e-3)


def test_portfolio_profitability_by_segment_default_dimensions(assumptions, small_portfolio):
    result = portfolio_profitability_by_segment(assumptions, small_portfolio)
    for column in SEGMENT_COLUMNS:
        assert column in result.columns
    assert result["policy_count"].sum() == len(small_portfolio)
    assert "pv_profit_margin" in result.columns
    assert "book_vs_indicated_premium_ratio" in result.columns


def test_portfolio_profitability_by_segment_custom_columns(assumptions, small_portfolio):
    priced = evaluate_portfolio_pricing(assumptions, small_portfolio)
    result = portfolio_profitability_by_segment(
        assumptions, small_portfolio, priced=priced, segment_columns=["sex", "smoker_status"]
    )
    assert list(result.columns[:2]) == ["sex", "smoker_status"]
    assert result["policy_count"].sum() == len(small_portfolio)


def test_portfolio_profitability_by_segment_rejects_unknown_column(assumptions, small_portfolio):
    with pytest.raises(PortfolioPricingError):
        portfolio_profitability_by_segment(assumptions, small_portfolio, segment_columns=["not_a_real_column"])


def test_portfolio_profitability_by_segment_merges_ae_when_exposures_supplied(assumptions, small_portfolio):
    priced = evaluate_portfolio_pricing(assumptions, small_portfolio)
    exposures = simulate_policy_exposures(assumptions, small_portfolio, random_seed=101)
    result = portfolio_profitability_by_segment(
        assumptions, small_portfolio, priced=priced, exposures=exposures
    )
    assert "ae_mortality" in result.columns
    assert "ae_lapse" in result.columns


def test_portfolio_profitability_by_segment_reuses_precomputed_priced(assumptions, small_portfolio):
    # Passing a precomputed `priced` should avoid re-solving and match a
    # from-scratch call exactly.
    priced = evaluate_portfolio_pricing(assumptions, small_portfolio)
    with_precomputed = portfolio_profitability_by_segment(assumptions, small_portfolio, priced=priced)
    from_scratch = portfolio_profitability_by_segment(assumptions, small_portfolio)
    assert np.allclose(with_precomputed["total_pv_profit"], from_scratch["total_pv_profit"])
