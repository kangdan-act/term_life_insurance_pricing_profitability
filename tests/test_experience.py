from copy import deepcopy
from pathlib import Path

import pytest

from life_pricing.config import ProjectAssumptions, load_assumptions
from life_pricing.experience import (
    EXPOSURE_COLUMNS,
    ExperienceAnalyticsError,
    actual_to_expected_by_segment,
    overall_actual_to_expected,
    simulate_policy_exposures,
)
from life_pricing.portfolio import generate_synthetic_portfolio

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "assumptions.yaml"


@pytest.fixture
def assumptions():
    return load_assumptions(CONFIG_PATH)


@pytest.fixture
def small_portfolio(assumptions):
    return generate_synthetic_portfolio(assumptions, n_policies=300, random_seed=11)


def test_exposure_schema(assumptions, small_portfolio):
    exposures = simulate_policy_exposures(assumptions, small_portfolio, random_seed=11)
    assert list(exposures.columns) == EXPOSURE_COLUMNS
    assert not exposures.empty


def test_exposures_reproducible_for_fixed_seed(assumptions, small_portfolio):
    a = simulate_policy_exposures(assumptions, small_portfolio, random_seed=5)
    b = simulate_policy_exposures(assumptions, small_portfolio, random_seed=5)
    assert a.equals(b)


def test_actual_indicators_are_zero_or_one(assumptions, small_portfolio):
    exposures = simulate_policy_exposures(assumptions, small_portfolio, random_seed=11)
    assert set(exposures["actual_death"].unique()) <= {0, 1}
    assert set(exposures["actual_lapse"].unique()) <= {0, 1}


def test_a_policy_never_has_both_actual_death_and_lapse_in_same_year(assumptions, small_portfolio):
    exposures = simulate_policy_exposures(assumptions, small_portfolio, random_seed=11)
    assert not ((exposures["actual_death"] == 1) & (exposures["actual_lapse"] == 1)).any()


def test_a_policy_has_no_exposure_rows_after_its_exit_year(assumptions, small_portfolio):
    exposures = simulate_policy_exposures(assumptions, small_portfolio, random_seed=11)
    for policy_id, group in exposures.groupby("policy_id"):
        years = group.sort_values("policy_year")["policy_year"].tolist()
        assert years == list(range(1, len(years) + 1))  # contiguous from year 1, no gaps
        exit_rows = group[(group["actual_death"] == 1) | (group["actual_lapse"] == 1)]
        if not exit_rows.empty:
            assert exit_rows["policy_year"].iloc[0] == years[-1]  # exit is the last row


def test_expected_qx_matches_pricing_mortality_curve(assumptions, small_portfolio):
    from life_pricing.mortality import mortality_curve_for_policy

    exposures = simulate_policy_exposures(assumptions, small_portfolio, random_seed=11)
    first_policy = small_portfolio.iloc[0]
    qx = mortality_curve_for_policy(
        assumptions,
        issue_age=first_policy.issue_age,
        sex=first_policy.sex,
        smoker_status=first_policy.smoker_status,
        underwriting_class=first_policy.underwriting_class,
    )
    policy_exposures = exposures[exposures["policy_id"] == first_policy.policy_id].sort_values("policy_year")
    for i, row in enumerate(policy_exposures.itertuples()):
        assert row.expected_qx == pytest.approx(qx[i])


def test_overall_ae_close_to_one_when_true_equals_expected(assumptions):
    raw = deepcopy(assumptions.raw)
    raw["experience_simulation"]["true_mortality_multiplier"] = 1.0
    raw["experience_simulation"]["true_lapse_multiplier"] = 1.0
    neutral = ProjectAssumptions(raw=raw)

    portfolio = generate_synthetic_portfolio(neutral, n_policies=5000, random_seed=3)
    exposures = simulate_policy_exposures(neutral, portfolio, random_seed=3)
    result = overall_actual_to_expected(exposures)

    assert result["ae_mortality"] == pytest.approx(1.0, abs=0.25)
    assert result["ae_lapse"] == pytest.approx(1.0, abs=0.15)


def test_overall_ae_reflects_configured_true_multipliers(assumptions):
    portfolio = generate_synthetic_portfolio(assumptions, n_policies=5000, random_seed=3)
    exposures = simulate_policy_exposures(assumptions, portfolio, random_seed=3)
    result = overall_actual_to_expected(exposures)

    # true_mortality_multiplier=1.15, true_lapse_multiplier=0.85 (config default)
    assert result["ae_mortality"] > 1.0
    assert result["ae_lapse"] < 1.0


def test_actual_to_expected_by_segment_default_dimensions(assumptions, small_portfolio):
    exposures = simulate_policy_exposures(assumptions, small_portfolio, random_seed=11)
    segmented = actual_to_expected_by_segment(exposures, small_portfolio)
    for col in ("issue_age_band", "sex", "smoker_status", "underwriting_class", "face_amount_band", "distribution_channel", "issue_cohort"):
        assert col in segmented.columns
    assert "ae_mortality" in segmented.columns
    assert "ae_lapse" in segmented.columns


def test_actual_to_expected_by_segment_custom_dimensions(assumptions, small_portfolio):
    exposures = simulate_policy_exposures(assumptions, small_portfolio, random_seed=11)
    segmented = actual_to_expected_by_segment(exposures, small_portfolio, segment_columns=["sex", "smoker_status"])
    assert list(segmented.columns[:2]) == ["sex", "smoker_status"]


def test_unknown_segment_column_raises(assumptions, small_portfolio):
    exposures = simulate_policy_exposures(assumptions, small_portfolio, random_seed=11)
    with pytest.raises(ExperienceAnalyticsError):
        actual_to_expected_by_segment(exposures, small_portfolio, segment_columns=["not_a_real_column"])


def test_empty_portfolio_rejected(assumptions):
    import pandas as pd

    from life_pricing.portfolio import POLICY_COLUMNS

    empty = pd.DataFrame(columns=POLICY_COLUMNS)
    with pytest.raises(ExperienceAnalyticsError):
        simulate_policy_exposures(assumptions, empty)


def test_empty_exposures_rejected_by_aggregation(assumptions, small_portfolio):
    import pandas as pd

    from life_pricing.experience import EXPOSURE_COLUMNS

    empty_exposures = pd.DataFrame(columns=EXPOSURE_COLUMNS)
    with pytest.raises(ExperienceAnalyticsError):
        actual_to_expected_by_segment(empty_exposures, small_portfolio)
    with pytest.raises(ExperienceAnalyticsError):
        overall_actual_to_expected(empty_exposures)
