from pathlib import Path

import numpy as np
import pytest

from life_pricing.config import load_assumptions
from life_pricing.portfolio import (
    POLICY_COLUMNS,
    PortfolioGenerationError,
    generate_synthetic_portfolio,
)

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "assumptions.yaml"


@pytest.fixture
def assumptions():
    return load_assumptions(CONFIG_PATH)


def test_generates_requested_row_count_and_columns(assumptions):
    df = generate_synthetic_portfolio(assumptions, n_policies=500, random_seed=1)
    assert len(df) == 500
    assert list(df.columns) == POLICY_COLUMNS


def test_policy_ids_are_unique(assumptions):
    df = generate_synthetic_portfolio(assumptions, n_policies=2000, random_seed=1)
    assert df["policy_id"].is_unique


def test_reproducible_for_fixed_seed(assumptions):
    a = generate_synthetic_portfolio(assumptions, n_policies=1000, random_seed=42)
    b = generate_synthetic_portfolio(assumptions, n_policies=1000, random_seed=42)
    pd_testing_ok = a.equals(b)
    assert pd_testing_ok


def test_different_seeds_produce_different_portfolios(assumptions):
    a = generate_synthetic_portfolio(assumptions, n_policies=1000, random_seed=1)
    b = generate_synthetic_portfolio(assumptions, n_policies=1000, random_seed=2)
    assert not a.equals(b)


def test_default_seed_and_count_come_from_assumptions(assumptions):
    df = generate_synthetic_portfolio(assumptions)
    assert len(df) == assumptions.n_policies
    df_explicit = generate_synthetic_portfolio(assumptions, n_policies=assumptions.n_policies, random_seed=assumptions.random_seed)
    assert df.equals(df_explicit)


def test_issue_age_within_configured_range(assumptions):
    df = generate_synthetic_portfolio(assumptions, n_policies=5000, random_seed=7)
    assert df["issue_age"].min() >= assumptions.issue_age_min
    assert df["issue_age"].max() <= assumptions.issue_age_max


def test_face_amount_within_configured_range_and_rounded(assumptions):
    df = generate_synthetic_portfolio(assumptions, n_policies=5000, random_seed=7)
    assert df["face_amount"].min() >= assumptions.face_amount_min
    assert df["face_amount"].max() <= assumptions.face_amount_max
    remainder = df["face_amount"] % assumptions.face_amount_round_to
    assert (remainder.abs() < 1e-6).all()


def test_categorical_fields_only_contain_configured_categories(assumptions):
    df = generate_synthetic_portfolio(assumptions, n_policies=5000, random_seed=7)
    assert set(df["sex"].unique()) <= set(assumptions.sex_distribution)
    assert set(df["smoker_status"].unique()) <= set(assumptions.smoker_distribution)
    assert set(df["underwriting_class"].unique()) <= set(assumptions.underwriting_class_distribution)
    assert set(df["distribution_channel"].unique()) <= set(assumptions.distribution_channel_distribution)
    assert set(df["state_region"].unique()) <= set(assumptions.state_region_distribution)


def test_issue_year_within_configured_range(assumptions):
    df = generate_synthetic_portfolio(assumptions, n_policies=5000, random_seed=7)
    assert df["issue_year"].min() >= assumptions.issue_year_min
    assert df["issue_year"].max() <= assumptions.issue_year_max


def test_term_years_matches_product_spec(assumptions):
    df = generate_synthetic_portfolio(assumptions, n_policies=200, random_seed=7)
    assert (df["term_years"] == assumptions.term_years).all()


def test_annual_premium_is_unset_pending_loop_5(assumptions):
    df = generate_synthetic_portfolio(assumptions, n_policies=200, random_seed=7)
    assert df["annual_premium"].isna().all()


def test_category_proportions_roughly_match_configured_weights(assumptions):
    df = generate_synthetic_portfolio(assumptions, n_policies=50_000, random_seed=99)
    observed = df["smoker_status"].value_counts(normalize=True).to_dict()
    expected = assumptions.smoker_distribution
    for category, expected_share in expected.items():
        assert observed[category] == pytest.approx(expected_share, abs=0.02)


def test_nonpositive_n_policies_is_rejected(assumptions):
    with pytest.raises(PortfolioGenerationError):
        generate_synthetic_portfolio(assumptions, n_policies=0, random_seed=1)
