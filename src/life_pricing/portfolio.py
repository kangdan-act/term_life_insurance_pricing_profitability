"""Synthetic portfolio generator (Loop 4).

Generates a reproducible synthetic book of 20-year term life policies whose
characteristics are drawn from configured (not hard-coded) distributions,
per PROJECT_SPEC.md section 3's required policy-level inputs. This gives
every downstream loop (pricing, profitability, experience analytics,
scenario testing) policy-level data to run against without depending on
real, non-public policyholder data.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from life_pricing.config import ProjectAssumptions

POLICY_COLUMNS = [
    "policy_id",
    "issue_age",
    "sex",
    "smoker_status",
    "underwriting_class",
    "face_amount",
    "term_years",
    "annual_premium",
    "issue_year",
    "distribution_channel",
    "state_region",
]


class PortfolioGenerationError(ValueError):
    """Raised when portfolio generation inputs are invalid."""


def _weighted_choice(rng: np.random.Generator, distribution: dict[str, float], size: int) -> np.ndarray:
    categories = list(distribution.keys())
    weights = np.array(list(distribution.values()), dtype=float)
    total = weights.sum()
    if total <= 0:
        raise PortfolioGenerationError("Distribution weights must sum to a positive number.")
    probabilities = weights / total
    return rng.choice(categories, size=size, p=probabilities)


def generate_synthetic_portfolio(
    assumptions: ProjectAssumptions,
    n_policies: int | None = None,
    random_seed: int | None = None,
) -> pd.DataFrame:
    """Generate a reproducible synthetic policy-level portfolio.

    Every categorical field is drawn from the distributions declared under
    `synthetic_data` in config/assumptions.yaml (not hard-coded here), and
    generation is fully reproducible for a fixed (n_policies, random_seed)
    pair (TEST_SPEC.md Gate E).

    `annual_premium` is left as NaN by design: Loop 5's gross premium engine
    is what solves/assigns premiums per policy. Loop 4 (this module) should
    not invent a pricing output ahead of the pricing engine that produces it
    (AGENTS.md: "do not invent ... when a configured [process] should
    supply [it]").
    """

    n = n_policies if n_policies is not None else assumptions.n_policies
    seed = random_seed if random_seed is not None else assumptions.random_seed

    if n <= 0:
        raise PortfolioGenerationError("n_policies must be positive.")

    rng = np.random.default_rng(seed)

    issue_age = rng.integers(assumptions.issue_age_min, assumptions.issue_age_max + 1, size=n)
    sex = _weighted_choice(rng, assumptions.sex_distribution, n)
    smoker_status = _weighted_choice(rng, assumptions.smoker_distribution, n)
    underwriting_class = _weighted_choice(rng, assumptions.underwriting_class_distribution, n)
    distribution_channel = _weighted_choice(rng, assumptions.distribution_channel_distribution, n)
    state_region = _weighted_choice(rng, assumptions.state_region_distribution, n)
    issue_year = rng.integers(assumptions.issue_year_min, assumptions.issue_year_max + 1, size=n)

    round_to = assumptions.face_amount_round_to
    raw_face = rng.uniform(assumptions.face_amount_min, assumptions.face_amount_max, size=n)
    face_amount = np.round(raw_face / round_to) * round_to
    face_amount = np.clip(face_amount, assumptions.face_amount_min, assumptions.face_amount_max)

    portfolio = pd.DataFrame(
        {
            "policy_id": [f"POL-{i + 1:06d}" for i in range(n)],
            "issue_age": issue_age.astype(int),
            "sex": sex,
            "smoker_status": smoker_status,
            "underwriting_class": underwriting_class,
            "face_amount": face_amount.astype(float),
            "term_years": assumptions.term_years,
            "annual_premium": np.nan,
            "issue_year": issue_year.astype(int),
            "distribution_channel": distribution_channel,
            "state_region": state_region,
        }
    )

    return portfolio[POLICY_COLUMNS]
