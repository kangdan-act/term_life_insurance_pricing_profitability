"""Experience analytics engine (Loop 8): actual-to-expected (A/E) mortality
and lapse analysis by portfolio segment.

This project has no real policyholder experience data (V1 is fully
synthetic and reproducible -- see docs/DATA_SOURCES.md). To still exercise
a genuine A/E analytics engine rather than a fabricated one, this module:

1. Treats the pricing assumptions (life_pricing.mortality's tables plus
   config/assumptions.yaml's lapse table) as the *expected* basis -- the
   exact same numbers the pricing engine (Loops 2-7) uses.
2. Simulates one stochastic *actual* outcome per policy-year of exposure,
   using a separately declared "true" experience basis
   (config/assumptions.yaml: experience_simulation.true_mortality_multiplier
   / true_lapse_multiplier), which deliberately differs from the pricing
   assumptions -- see ACTUARIAL_ASSUMPTIONS.md -- so the resulting A/E
   ratios are not trivially 1.0.

Per AGENTS.md's rule against mixing actual experience with expected
assumptions without labeling them: every function and output column here is
named `actual_*` or `expected_*` accordingly, and the exposure simulation
never feeds back into the pricing engine.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from life_pricing.config import ProjectAssumptions
from life_pricing.mortality import mortality_curve_for_policy

EXPOSURE_COLUMNS = [
    "policy_id",
    "policy_year",
    "expected_qx",
    "expected_lapse_rate",
    "actual_death",
    "actual_lapse",
]

DEFAULT_SEGMENT_COLUMNS = [
    "issue_age_band",
    "sex",
    "smoker_status",
    "underwriting_class",
    "face_amount_band",
    "distribution_channel",
    "issue_cohort",
]


class ExperienceAnalyticsError(ValueError):
    """Raised when experience simulation or A/E aggregation inputs are invalid."""


def _issue_age_band(issue_age: int) -> str:
    """Illustrative reporting bucket -- not an actuarial assumption, just a
    display grouping for portfolio-level A/E tables."""
    if issue_age < 35:
        return "25-34"
    if issue_age < 45:
        return "35-44"
    if issue_age < 55:
        return "45-54"
    return "55-60"


def _face_amount_band(face_amount: float) -> str:
    """Illustrative reporting bucket -- see _issue_age_band."""
    if face_amount < 250_000:
        return "100k-249k"
    if face_amount < 500_000:
        return "250k-499k"
    if face_amount < 750_000:
        return "500k-749k"
    return "750k-1000k"


def simulate_policy_exposures(
    assumptions: ProjectAssumptions,
    portfolio: pd.DataFrame,
    random_seed: int | None = None,
) -> pd.DataFrame:
    """Simulate one policy-year exposure record per (policy, in-force year).

    A policy contributes one row per policy year it is actually in force,
    stopping at (and including) the year it dies, lapses, or completes the
    full term. `expected_qx` / `expected_lapse_rate` are the pricing
    (expected) rates for that policy-year; `actual_death` / `actual_lapse`
    are 0/1 indicators drawn from the separately declared "true" basis.
    Mortality is drawn first each year (consistent with the competing
    decrement ordering D_t = I_t*q_t, L_t = I_t*(1-q_t)*l_t used throughout
    this project): a policy can only lapse in a year it did not die.
    """

    if portfolio.empty:
        raise ExperienceAnalyticsError("portfolio must contain at least one policy.")

    seed = random_seed if random_seed is not None else assumptions.random_seed
    rng = np.random.default_rng(seed)

    true_mortality_multiplier = assumptions.true_mortality_multiplier
    true_lapse_multiplier = assumptions.true_lapse_multiplier
    lapse_rates = assumptions.lapse_rates
    term_years = assumptions.term_years

    mortality_cache: dict[tuple, list[float]] = {}
    rows: list[tuple] = []

    for policy in portfolio.itertuples(index=False):
        cache_key = (policy.issue_age, policy.sex, policy.smoker_status, policy.underwriting_class)
        if cache_key not in mortality_cache:
            mortality_cache[cache_key] = mortality_curve_for_policy(
                assumptions,
                issue_age=policy.issue_age,
                sex=policy.sex,
                smoker_status=policy.smoker_status,
                underwriting_class=policy.underwriting_class,
            )
        expected_qx_curve = mortality_cache[cache_key]

        for t in range(1, term_years + 1):
            expected_qx = expected_qx_curve[t - 1]
            expected_lapse_rate = lapse_rates[t]

            true_qx = min(max(expected_qx * true_mortality_multiplier, 0.0), 1.0)
            true_lapse_rate = min(max(expected_lapse_rate * true_lapse_multiplier, 0.0), 1.0)

            actual_death = 1 if rng.random() < true_qx else 0
            actual_lapse = 0
            if not actual_death:
                actual_lapse = 1 if rng.random() < true_lapse_rate else 0

            rows.append((policy.policy_id, t, expected_qx, expected_lapse_rate, actual_death, actual_lapse))

            if actual_death or actual_lapse:
                break

    return pd.DataFrame(rows, columns=EXPOSURE_COLUMNS)


def _add_segment_columns(portfolio: pd.DataFrame) -> pd.DataFrame:
    portfolio = portfolio.copy()
    portfolio["issue_age_band"] = portfolio["issue_age"].apply(_issue_age_band)
    portfolio["face_amount_band"] = portfolio["face_amount"].apply(_face_amount_band)
    portfolio["issue_cohort"] = portfolio["issue_year"]
    return portfolio


def actual_to_expected_by_segment(
    exposures: pd.DataFrame,
    portfolio: pd.DataFrame,
    segment_columns: list[str] | None = None,
) -> pd.DataFrame:
    """Aggregate simulated exposures into A/E mortality and lapse ratios by segment.

    A/E mortality = sum(actual_death) / sum(expected_qx) over all exposure
    rows in the segment; A/E lapse = sum(actual_lapse) / sum(expected_lapse_rate),
    both standard actuarial experience-study ratios.
    """

    if exposures.empty:
        raise ExperienceAnalyticsError("exposures must contain at least one row.")

    columns = segment_columns if segment_columns is not None else DEFAULT_SEGMENT_COLUMNS

    portfolio_bands = _add_segment_columns(portfolio)
    unknown_columns = set(columns) - set(portfolio_bands.columns)
    if unknown_columns:
        raise ExperienceAnalyticsError(f"Unknown segment column(s): {sorted(unknown_columns)}")

    merged = exposures.merge(portfolio_bands[["policy_id"] + columns], on="policy_id", how="left")

    grouped = (
        merged.groupby(columns, observed=True)
        .agg(
            policy_year_exposures=("policy_id", "count"),
            expected_deaths=("expected_qx", "sum"),
            actual_deaths=("actual_death", "sum"),
            expected_lapses=("expected_lapse_rate", "sum"),
            actual_lapses=("actual_lapse", "sum"),
        )
        .reset_index()
    )

    grouped["ae_mortality"] = grouped["actual_deaths"] / grouped["expected_deaths"]
    grouped["ae_lapse"] = grouped["actual_lapses"] / grouped["expected_lapses"]

    return grouped


def overall_actual_to_expected(exposures: pd.DataFrame) -> dict[str, float]:
    """Portfolio-wide A/E mortality and lapse ratios (no segmentation)."""

    if exposures.empty:
        raise ExperienceAnalyticsError("exposures must contain at least one row.")

    expected_deaths = exposures["expected_qx"].sum()
    actual_deaths = exposures["actual_death"].sum()
    expected_lapses = exposures["expected_lapse_rate"].sum()
    actual_lapses = exposures["actual_lapse"].sum()

    return {
        "expected_deaths": float(expected_deaths),
        "actual_deaths": float(actual_deaths),
        "ae_mortality": float(actual_deaths / expected_deaths),
        "expected_lapses": float(expected_lapses),
        "actual_lapses": float(actual_lapses),
        "ae_lapse": float(actual_lapses / expected_lapses),
    }
