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
        face_amount=first_policy.face_amount,
    )
    policy_exposures = exposures[exposures["policy_id"] == first_policy.policy_id].sort_values("policy_year")
    for i, row in enumerate(policy_exposures.itertuples()):
        assert row.expected_qx == pytest.approx(qx[i])


def test_expected_probability_columns_match_competing_decrement_identity(assumptions, small_portfolio):
    # V1.1: expected_death_probability = expected_qx (D_t = I_t*q_t, and
    # each exposure row already represents one unit of I_t); and
    # expected_lapse_probability = (1-expected_qx)*expected_lapse_rate
    # (L_t = I_t*(1-q_t)*l_t), matching the competing-decrement identities
    # in PROJECT_SPEC.md section 7 and the ordering the actual-outcome
    # simulation below already uses (mortality sampled before lapse).
    exposures = simulate_policy_exposures(assumptions, small_portfolio, random_seed=11)
    assert (exposures["expected_death_probability"] == exposures["expected_qx"]).all()
    expected_lapse_probability = (1.0 - exposures["expected_qx"]) * exposures["expected_lapse_rate"]
    assert exposures["expected_lapse_probability"].to_numpy() == pytest.approx(
        expected_lapse_probability.to_numpy()
    )
    # The corrected denominator is always <= the old (buggy) raw-rate
    # denominator, since (1-q_t) <= 1 -- confirming the fix can only ever
    # raise the reported A/E lapse ratio relative to the old code, not
    # lower it, which is the direction the bug report described.
    assert (exposures["expected_lapse_probability"] <= exposures["expected_lapse_rate"]).all()


def test_ae_lapse_denominator_uses_competing_decrement_not_raw_rate(assumptions, small_portfolio):
    # Direct regression test for the A/E-lapse fix: overall_actual_to_expected
    # must divide by sum(expected_lapse_probability), not sum(expected_lapse_rate).
    exposures = simulate_policy_exposures(assumptions, small_portfolio, random_seed=11)
    result = overall_actual_to_expected(exposures)

    correct_denominator = exposures["expected_lapse_probability"].sum()
    buggy_denominator = exposures["expected_lapse_rate"].sum()
    actual_lapses = exposures["actual_lapse"].sum()

    assert result["expected_lapses"] == pytest.approx(correct_denominator)
    assert result["ae_lapse"] == pytest.approx(actual_lapses / correct_denominator)
    # The buggy denominator is strictly larger here (mortality rates are
    # positive for every exposure row), so the old code would have reported
    # a materially smaller (understated) A/E lapse ratio.
    assert correct_denominator < buggy_denominator
    assert result["ae_lapse"] > actual_lapses / buggy_denominator


def test_overall_ae_close_to_one_when_true_equals_expected(assumptions):
    raw = deepcopy(assumptions.raw)
    raw["experience_simulation"]["true_mortality_multiplier_by_duration"] = {
        duration: 1.0 for duration in raw["experience_simulation"]["true_mortality_multiplier_by_duration"]
    }
    raw["experience_simulation"]["true_lapse_multiplier_by_duration"] = {
        duration: 1.0 for duration in raw["experience_simulation"]["true_lapse_multiplier_by_duration"]
    }
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

    # config default (Loop 12): true_mortality_multiplier_by_duration is the
    # real SOA-ILEC-derived curve, entirely < 1.0 (0.7354-0.9093), so actual
    # mortality runs lower than expected. true_lapse_multiplier_by_duration
    # (Loop 12b) is also real -- derived from a real-vs-real risk-class
    # comparison within the same persistency study -- and is > 1.0 for most
    # durations (early durations, which dominate portfolio exposure by
    # policy-year count, run higher) except at duration 20, where it dips
    # below 1.0; the population-weighted aggregate lands modestly above
    # 1.0. Unlike the flat-scalar predecessor, this is a genuine, real,
    # non-monotonic pattern rather than an arbitrary constant -- the test
    # below checks it materially differs from the trivial 1.0 case (already
    # covered by test_overall_ae_close_to_one_when_true_equals_expected)
    # rather than asserting one fixed direction that a future data
    # refinement could reasonably flip.
    assert result["ae_mortality"] < 1.0
    assert abs(result["ae_lapse"] - 1.0) > 0.02


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
