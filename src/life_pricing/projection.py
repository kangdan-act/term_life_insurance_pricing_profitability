"""Core actuarial projection engine.

Implements Loop 2 of the roadmap: survival, mortality, lapse, in-force
tracking, and discounting for a single policy, following the actuarial
identities declared in PROJECT_SPEC.md section 7.

Premiums, expenses, and net cash flow are intentionally out of scope here
(they belong to Loops 5-7) so this module has exactly one job: turn a
mortality curve plus the configured lapse/interest assumptions into a
per-policy-year decrement and discounting schedule.

V1.1 timing correction: PROJECT_SPEC.md section 2 has always specified
"Premium mode: Annual, beginning of policy year while in force" and
"Benefit timing: End of policy year of death" -- but V1's code discounted
every cash-flow component with one uniform end-of-year factor
`v_t = (1+i)^-t`, silently ignoring the beginning-of-year premium timing
the spec itself declared. This module now computes THREE discount-factor
columns instead of one, matching each cash-flow component's own timing
(see PROJECT_SPEC.md section 7 and ACTUARIAL_ASSUMPTIONS.md for the full
rationale and the explicit choice of mid-year timing for maintenance
expense):

- `discount_factor` (unchanged formula, v_t = (1+i)^-t): end-of-year --
  used for the death benefit/claim, per section 2's benefit timing.
- `discount_factor_premium` (v_t = (1+i)^-(t-1)): beginning-of-year --
  used for the premium itself, and for every expense component that is
  incurred at the same moment premium is collected (the acquisition fixed
  cost and the acquisition/renewal percent-of-premium expense, both
  incurred at issue/renewal).
- `discount_factor_maintenance` (v_t = (1+i)^-(t-0.5)): mid-year -- used
  for the ongoing per-in-force-policy maintenance expense, modeling it as
  spread through the policy year rather than concentrated at either
  endpoint.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from life_pricing.config import ProjectAssumptions


class ProjectionInputError(ValueError):
    """Raised when inputs to the projection engine are invalid."""


@dataclass(frozen=True)
class PolicyYearProjection:
    """One row of the per-policy-year projection (PROJECT_SPEC.md section 4).

    Three discount factors are exposed (V1.1) because premium, claim, and
    maintenance expense are no longer assumed to occur at the same moment
    within the policy year -- see this module's docstring.
    """

    policy_year: int
    attained_age: int
    beginning_inforce_probability: float
    mortality_rate_qx: float
    lapse_rate: float
    death_probability: float
    lapse_probability: float
    ending_inforce_probability: float
    discount_factor: float
    discount_factor_premium: float
    discount_factor_maintenance: float
    expected_death_benefit: float


def _validate_inputs(
    assumptions: ProjectAssumptions,
    issue_age: int,
    mortality_rates_qx: Sequence[float],
    face_amount: float,
) -> None:
    term_years = assumptions.term_years

    if len(mortality_rates_qx) != term_years:
        raise ProjectionInputError(
            f"mortality_rates_qx must have exactly {term_years} entries "
            f"(one per policy year), got {len(mortality_rates_qx)}."
        )

    for t, q in enumerate(mortality_rates_qx, start=1):
        if not 0.0 <= q <= 1.0:
            raise ProjectionInputError(
                f"mortality_rate_qx for policy year {t} must be in [0, 1], got {q}."
            )

    if not assumptions.issue_age_min <= issue_age <= assumptions.issue_age_max:
        raise ProjectionInputError(
            f"issue_age {issue_age} is outside the configured range "
            f"[{assumptions.issue_age_min}, {assumptions.issue_age_max}]."
        )

    if face_amount <= 0:
        raise ProjectionInputError("face_amount must be positive.")


def project_policy(
    assumptions: ProjectAssumptions,
    issue_age: int,
    mortality_rates_qx: Sequence[float],
    face_amount: float,
) -> list[PolicyYearProjection]:
    """Project one policy's decrements and discounting over the full term.

    Implements PROJECT_SPEC.md section 7 core actuarial identities:
        I_1 = 1
        D_t = I_t * q_t
        L_t = I_t * (1 - q_t) * l_t
        I_(t+1) = I_t * (1 - q_t) * (1 - l_t)
        v_t = (1 + i)^(-t)                    [end-of-year; claim timing]
        v_t^premium = (1 + i)^(-(t-1))        [beginning-of-year; V1.1]
        v_t^maintenance = (1 + i)^(-(t-0.5))  [mid-year; V1.1]
        Claim_t = D_t * Face

    `mortality_rates_qx` must be supplied by the caller (one q_x per policy
    year, attained-age ordered) -- this engine does not invent or look up
    mortality rates itself. Wiring in a real mortality table is Loop 3's
    job (see AGENTS.md: "Do not invent mortality rates when a configured
    table should supply them.").

    Premiums, expenses, and net cash flow are added in later loops.
    """

    _validate_inputs(assumptions, issue_age, mortality_rates_qx, face_amount)

    lapse_rates = assumptions.lapse_rates
    discount_rate = assumptions.discount_rate

    records: list[PolicyYearProjection] = []
    beginning_inforce = 1.0

    for t in range(1, assumptions.term_years + 1):
        q_t = float(mortality_rates_qx[t - 1])
        l_t = lapse_rates[t]

        death_probability = beginning_inforce * q_t
        lapse_probability = beginning_inforce * (1.0 - q_t) * l_t
        ending_inforce = beginning_inforce * (1.0 - q_t) * (1.0 - l_t)
        discount_factor = (1.0 + discount_rate) ** (-t)
        discount_factor_premium = (1.0 + discount_rate) ** (-(t - 1))
        discount_factor_maintenance = (1.0 + discount_rate) ** (-(t - 0.5))
        expected_death_benefit = death_probability * face_amount

        records.append(
            PolicyYearProjection(
                policy_year=t,
                attained_age=issue_age + t - 1,
                beginning_inforce_probability=beginning_inforce,
                mortality_rate_qx=q_t,
                lapse_rate=l_t,
                death_probability=death_probability,
                lapse_probability=lapse_probability,
                ending_inforce_probability=ending_inforce,
                discount_factor=discount_factor,
                discount_factor_premium=discount_factor_premium,
                discount_factor_maintenance=discount_factor_maintenance,
                expected_death_benefit=expected_death_benefit,
            )
        )

        beginning_inforce = ending_inforce

    return records


def to_dataframe(records: list[PolicyYearProjection]):
    """Convenience conversion to a pandas DataFrame for downstream loops."""

    import pandas as pd

    return pd.DataFrame([r.__dict__ for r in records])
