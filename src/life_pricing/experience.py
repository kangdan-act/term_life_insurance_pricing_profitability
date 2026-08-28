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
   (config/assumptions.yaml: experience_simulation
   .true_mortality_multiplier_by_duration / true_lapse_multiplier_by_duration),
   which deliberately differs from the pricing assumptions -- see
   ACTUARIAL_ASSUMPTIONS.md -- so the resulting A/E ratios are not
   trivially 1.0. Both multipliers vary by policy duration and are derived
   from real SOA data (ILEC 2012-2019 for mortality, 2009-13 Persistency
   Update's by-risk-class cut for lapse) -- see docs/DATA_SOURCES.md.

Per AGENTS.md's rule against mixing actual experience with expected
assumptions without labeling them: every function and output column here is
named `actual_*` or `expected_*` accordingly, and the exposure simulation
never feeds back into the pricing engine.

V1.1 A/E-lapse correction: this project's competing-decrement ordering
(PROJECT_SPEC.md section 7) always applies mortality before lapse within a
policy year -- D_t = I_t*q_t, L_t = I_t*(1-q_t)*l_t -- and
`simulate_policy_exposures` below already samples the *actual* outcome that
way (a policy can only be sampled to lapse in a year it did not die). But
the A/E aggregation functions previously summed the raw expected lapse
RATE `l_t` as the "expected lapses" denominator for every exposure row,
which is not the same thing: `l_t` is the probability of lapsing *given*
the policy is already known to be in force at the start of year t, not the
probability of lapsing unconditionally within year t once mortality is
also in play. Since `actual_lapse` can only be 1 in a year the policy did
not die, comparing sum(actual_lapse) against sum(l_t) systematically
understates A/E lapse (the denominator is too large by ignoring the
"survived mortality this year" condition). The correct per-exposure
expected lapse probability is `(1-q_t)*l_t`, matching L_t's own identity --
exposed here as `expected_lapse_probability` (alongside
`expected_death_probability`, an alias for `expected_qx` kept for
symmetry), and used as the A/E lapse denominator in
`actual_to_expected_by_segment` / `overall_actual_to_expected` below.
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
    "expected_death_probability",
    "expected_lapse_probability",
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


def issue_age_band(issue_age: int) -> str:
    """Illustrative reporting bucket -- not an actuarial assumption, just a
    display grouping for portfolio-level A/E and profitability tables.
    Public (V1.1) so life_pricing.portfolio_pricing can group policies into
    the same segments for its own PROJECT_SPEC.md section 6 rollups."""
    if issue_age < 35:
        return "25-34"
    if issue_age < 45:
        return "35-44"
    if issue_age < 55:
        return "45-54"
    return "55-60"


def face_amount_band(face_amount: float) -> str:
    """Illustrative reporting bucket -- see issue_age_band."""
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
    (expected) RATES for that policy-year; `expected_death_probability` /
    `expected_lapse_probability` (V1.1) are the corresponding per-exposure
    PROBABILITIES under the competing-decrement ordering
    (`expected_death_probability = expected_qx`,
    `expected_lapse_probability = (1 - expected_qx) * expected_lapse_rate`)
    -- these, not the raw rates, are what the A/E aggregation functions
    below should sum as their denominators (see module docstring).
    `actual_death` / `actual_lapse` are 0/1 indicators drawn from the
    separately declared "true" basis. Mortality is drawn first each year
    (consistent with the competing decrement ordering
    D_t = I_t*q_t, L_t = I_t*(1-q_t)*l_t used throughout this project): a
    policy can only lapse in a year it did not die -- exactly what
    `expected_lapse_probability` reflects on the expected side.
    """

    if portfolio.empty:
        raise ExperienceAnalyticsError("portfolio must contain at least one policy.")

    seed = random_seed if random_seed is not None else assumptions.random_seed
    rng = np.random.default_rng(seed)

    true_mortality_multiplier_by_duration = assumptions.true_mortality_multiplier_by_duration
    true_lapse_multiplier_by_duration = assumptions.true_lapse_multiplier_by_duration
    lapse_rates = assumptions.lapse_rates
    term_years = assumptions.term_years

    mortality_cache: dict[tuple, list[float]] = {}
    rows: list[tuple] = []

    for policy in portfolio.itertuples(index=False):
        cache_key = (
            policy.issue_age,
            policy.sex,
            policy.smoker_status,
            policy.underwriting_class,
            policy.face_amount,
        )
        if cache_key not in mortality_cache:
            mortality_cache[cache_key] = mortality_curve_for_policy(
                assumptions,
                issue_age=policy.issue_age,
                sex=policy.sex,
                smoker_status=policy.smoker_status,
                underwriting_class=policy.underwriting_class,
                face_amount=policy.face_amount,
            )
        expected_qx_curve = mortality_cache[cache_key]

        for t in range(1, term_years + 1):
            expected_qx = expected_qx_curve[t - 1]
            expected_lapse_rate = lapse_rates[t]

            true_mortality_multiplier = true_mortality_multiplier_by_duration[t]
            true_lapse_multiplier = true_lapse_multiplier_by_duration[t]
            true_qx = min(max(expected_qx * true_mortality_multiplier, 0.0), 1.0)
            true_lapse_rate = min(max(expected_lapse_rate * true_lapse_multiplier, 0.0), 1.0)

            actual_death = 1 if rng.random() < true_qx else 0
            actual_lapse = 0
            if not actual_death:
                actual_lapse = 1 if rng.random() < true_lapse_rate else 0

            expected_death_probability = expected_qx
            expected_lapse_probability = (1.0 - expected_qx) * expected_lapse_rate

            rows.append(
                (
                    policy.policy_id,
                    t,
                    expected_qx,
                    expected_lapse_rate,
                    expected_death_probability,
                    expected_lapse_probability,
                    actual_death,
                    actual_lapse,
                )
            )

            if actual_death or actual_lapse:
                break

    return pd.DataFrame(rows, columns=EXPOSURE_COLUMNS)


def _add_segment_columns(portfolio: pd.DataFrame) -> pd.DataFrame:
    portfolio = portfolio.copy()
    portfolio["issue_age_band"] = portfolio["issue_age"].apply(issue_age_band)
    portfolio["face_amount_band"] = portfolio["face_amount"].apply(face_amount_band)
    portfolio["issue_cohort"] = portfolio["issue_year"]
    return portfolio


def actual_to_expected_by_segment(
    exposures: pd.DataFrame,
    portfolio: pd.DataFrame,
    segment_columns: list[str] | None = None,
) -> pd.DataFrame:
    """Aggregate simulated exposures into A/E mortality and lapse ratios by segment.

    A/E mortality = sum(actual_death) / sum(expected_death_probability);
    A/E lapse = sum(actual_lapse) / sum(expected_lapse_probability), both
    standard actuarial experience-study ratios. V1.1: the lapse denominator
    uses `expected_lapse_probability` = (1-expected_qx)*expected_lapse_rate,
    not the raw expected lapse rate -- see module docstring for why.
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
            expected_deaths=("expected_death_probability", "sum"),
            actual_deaths=("actual_death", "sum"),
            expected_lapses=("expected_lapse_probability", "sum"),
            actual_lapses=("actual_lapse", "sum"),
        )
        .reset_index()
    )

    grouped["ae_mortality"] = grouped["actual_deaths"] / grouped["expected_deaths"]
    grouped["ae_lapse"] = grouped["actual_lapses"] / grouped["expected_lapses"]

    return grouped


def overall_actual_to_expected(exposures: pd.DataFrame) -> dict[str, float]:
    """Portfolio-wide A/E mortality and lapse ratios (no segmentation).

    V1.1: the lapse denominator uses `expected_lapse_probability` =
    (1-expected_qx)*expected_lapse_rate, not the raw expected lapse rate --
    see module docstring for why.
    """

    if exposures.empty:
        raise ExperienceAnalyticsError("exposures must contain at least one row.")

    expected_deaths = exposures["expected_death_probability"].sum()
    actual_deaths = exposures["actual_death"].sum()
    expected_lapses = exposures["expected_lapse_probability"].sum()
    actual_lapses = exposures["actual_lapse"].sum()

    return {
        "expected_deaths": float(expected_deaths),
        "actual_deaths": float(actual_deaths),
        "ae_mortality": float(actual_deaths / expected_deaths),
        "expected_lapses": float(expected_lapses),
        "actual_lapses": float(actual_lapses),
        "ae_lapse": float(actual_lapses / expected_lapses),
    }
