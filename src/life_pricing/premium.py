"""Gross premium engine (Loop 5).

Solves the annual level premium P that hits a target PV profit margin,
in closed form.

Every net-cash-flow component is linear in P:
    Prem_t(P)    = I_t * P
    Expense_t(P) = fixed_t + coef_t * P
        fixed_t = (acquisition_fixed if t==1 else 0) + maintenance_per_inforce_year * I_t
        coef_t  = acquisition_pct_first_year_premium [t=1] or renewal_pct_premium [t>1]  (times I_t)
    NetCashFlow_t(P) = Prem_t(P) - Claim_t - Expense_t(P) = P*(I_t - coef_t) - (Claim_t + fixed_t)

Summed and discounted:
    PVProfit(P)  = P * A - B,   A = sum v_t*(I_t - coef_t),  B = sum v_t*(Claim_t + fixed_t)
    PVPremium(P) = P * C,       C = sum v_t * I_t

Setting PVProfit(P) / PVPremium(P) = target_margin and solving for P gives:
    P = B / (A - target_margin * C)

`fixed_t` and `coef_t` are not re-derived here by hand -- they are read off
life_pricing.cashflow.year_expenses() evaluated at a unit premium (P=1), so
this solver can never silently drift from the expense logic that
build_policy_cash_flows() uses once P is known. That shared source of truth
is what makes "solve for the target premium, then rebuild cash flows with
it and check the margin comes back out" (TEST_SPEC.md Gate C) a genuine
correctness check rather than a tautology.
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
        discount_factor = row.discount_factor
        claim = row.expected_death_benefit

        # Evaluate year_expenses() at a unit premium (expected_premium = I_t
        # * 1) to read off fixed_t and coef_t without duplicating the
        # acquisition/renewal/maintenance logic that lives in cashflow.py.
        acquisition_expense, maintenance_expense, premium_related_at_unit_premium = year_expenses(
            assumptions, row.policy_year, beginning_inforce, expected_premium=beginning_inforce
        )
        fixed_t = acquisition_expense + maintenance_expense
        coef_t = premium_related_at_unit_premium

        A += discount_factor * (beginning_inforce - coef_t)
        B += discount_factor * (claim + fixed_t)
        C += discount_factor * beginning_inforce

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
