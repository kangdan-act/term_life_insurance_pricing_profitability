"""Gross premium engine (Loop 5).

Solves the annual level premium P that hits a target PV profit margin,
in closed form.

V1.1 timing correction: premium, claim, and maintenance expense are no
longer assumed to occur at the same moment (see life_pricing.projection's
module docstring and ACTUARIAL_ASSUMPTIONS.md) -- premium and the
premium-related/acquisition expenses use the beginning-of-year discount
factor v_b(t), the claim uses the end-of-year factor v_e(t) (unchanged),
and maintenance expense uses the mid-year factor v_m(t). Every net-cash-flow
component is still linear in P, so the closed-form re-derivation keeps the
exact same shape as V1 -- only which discount factor multiplies which term
changes:
    Prem_t(P)              = I_t * P                     (discounted at v_b(t))
    AcqFixed_t              = acquisition_fixed [t=1 only] (discounted at v_b(t))
    PremiumRelatedExpense_t(P) = coef_t * P               (discounted at v_b(t))
        coef_t  = (acquisition_pct_first_year_premium [t=1] or
                   renewal_pct_premium [t>1]) * I_t
    Maintenance_t            = maintenance_per_inforce_year * I_t (discounted at v_m(t))
    Claim_t                                                (discounted at v_e(t))

    PVProfit(P)  = P * A - B
        A = sum v_b(t) * (I_t - coef_t)
        B = sum v_e(t)*Claim_t + sum v_b(t)*AcqFixed_t + sum v_m(t)*Maintenance_t
    PVPremium(P) = P * C
        C = sum v_b(t) * I_t

Setting PVProfit(P) / PVPremium(P) = target_margin and solving for P gives
the same closed form as V1:
    P = B / (A - target_margin * C)

`AcqFixed_t`, `Maintenance_t`, and `coef_t` are not re-derived here by
hand -- they are read off life_pricing.cashflow.year_expenses() evaluated
at a unit premium (P=1), so this solver can never silently drift from the
expense logic that build_policy_cash_flows() uses once P is known. That
shared source of truth is what makes "solve for the target premium, then
rebuild cash flows with it and check the margin comes back out"
(TEST_SPEC.md Gate C) a genuine correctness check rather than a tautology.
"""

from __future__ import annotations

from life_pricing.cashflow import year_expenses
from life_pricing.config import ProjectAssumptions
from life_pricing.projection import PolicyYearProjection


class PremiumSolveError(ValueError):
    """Raised when no valid premium can be solved for the given inputs."""


def solve_annual_premium(
    assumptions: ProjectAssumptions,
    projection: list[PolicyYearProjection],
    target_margin: float | None = None,
) -> float:
    """Solve for the annual level premium P satisfying PVProfit/PVPremium = target_margin.

    `target_margin` defaults to `assumptions.target_profit_margin`; pass
    0.0 explicitly for the break-even premium.
    """

    if not projection:
        raise PremiumSolveError("projection must contain at least one policy year.")

    margin = assumptions.target_profit_margin if target_margin is None else target_margin
    if not 0.0 <= margin < 1.0:
        raise PremiumSolveError(f"target_margin must be in [0, 1), got {margin}.")

    A = 0.0
    B = 0.0
    C = 0.0

    for row in projection:
        beginning_inforce = row.beginning_inforce_probability
        v_premium = row.discount_factor_premium
        v_claim = row.discount_factor
        v_maintenance = row.discount_factor_maintenance
        claim = row.expected_death_benefit

        # Evaluate year_expenses() at a unit premium (expected_premium = I_t
        # * 1) to read off acquisition_expense/maintenance_expense/coef_t
        # without duplicating the acquisition/renewal/maintenance logic
        # that lives in cashflow.py.
        acquisition_expense, maintenance_expense, premium_related_at_unit_premium = year_expenses(
            assumptions, row.policy_year, beginning_inforce, expected_premium=beginning_inforce
        )
        coef_t = premium_related_at_unit_premium

        # V1.1: acquisition_expense and the premium-related coefficient
        # share premium's beginning-of-year timing; maintenance keeps its
        # own mid-year timing; the claim keeps its own end-of-year timing.
        A += v_premium * (beginning_inforce - coef_t)
        B += v_claim * claim + v_premium * acquisition_expense + v_maintenance * maintenance_expense
        C += v_premium * beginning_inforce

    denominator = A - margin * C
    if denominator <= 0:
        raise PremiumSolveError(
            "No positive premium satisfies the target margin with these assumptions "
            f"(A - target_margin*C = {denominator} <= 0)."
        )

    premium = B / denominator

    if premium <= 0:
        raise PremiumSolveError(f"Solved premium is not positive ({premium}); check inputs.")

    return premium


def solve_break_even_premium(
    assumptions: ProjectAssumptions, projection: list[PolicyYearProjection]
) -> float:
    """Convenience wrapper: the premium that makes PV profit exactly zero."""

    return solve_annual_premium(assumptions, projection, target_margin=0.0)
