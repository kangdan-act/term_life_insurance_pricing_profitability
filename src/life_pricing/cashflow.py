"""Expense & profitability engine (Loops 6-7).

Turns a Loop 2 decrement/discounting projection plus a chosen annual level
premium into the full per-policy-year cash flow (PROJECT_SPEC.md section 4)
and the policy-level summary (section 5): expenses, net cash flow, PV
profit, and PV profit margin.

`year_expenses()` is the single source of truth for how expenses split
between the part that's independent of premium (acquisition fixed cost,
maintenance) and the part that scales with premium (acquisition % and
renewal % of premium). life_pricing.premium reuses this exact function
(evaluated at a unit premium) to derive its closed-form premium solve, so
the solver and the cash-flow builder can never silently drift apart.
"""

from __future__ import annotations

from dataclasses import dataclass

from life_pricing.config import ProjectAssumptions
from life_pricing.projection import PolicyYearProjection


class CashFlowError(ValueError):
    """Raised when cash-flow construction inputs are invalid."""


@dataclass(frozen=True)
class PolicyYearCashFlow:
    """One row of the full per-policy-year output (PROJECT_SPEC.md section 4)."""

    policy_year: int
    attained_age: int
    beginning_inforce_probability: float
    mortality_rate_qx: float
    lapse_rate: float
    death_probability: float
    lapse_probability: float
    ending_inforce_probability: float
    discount_factor: float
    expected_premium: float
    expected_death_benefit: float
    acquisition_expense: float
    maintenance_expense: float
    premium_related_expense: float
    net_cash_flow: float
    present_value_net_cash_flow: float


@dataclass(frozen=True)
class PolicySummary:
    """Policy-level summary outputs (PROJECT_SPEC.md section 5)."""

    pv_premiums: float
    pv_claims: float
    pv_expenses: float
    pv_profit: float
    pv_profit_margin: float


def year_expenses(
    assumptions: ProjectAssumptions,
    policy_year: int,
    beginning_inforce: float,
    expected_premium: float,
) -> tuple[float, float, float]:
    """Return (acquisition_expense, maintenance_expense, premium_related_expense).

    - acquisition_expense: the fixed per-policy acquisition cost, incurred
      once at issue (policy year 1 only), certain given the policy was
      issued (beginning in-force in year 1 is always 1 by construction).
      Independent of premium.
    - maintenance_expense: per-in-force-policy annual cost, every policy
      year, proportional to beginning in-force probability. Independent of
      premium.
    - premium_related_expense: percentage-of-premium expense. Year 1 uses
      the acquisition percentage (first-year expense/commission load);
      years 2+ use the renewal percentage. Proportional to
      `expected_premium` (= beginning_inforce * annual_premium), i.e. the
      premium actually expected to be collected that year, not the gross
      contractual premium.
    """

    maintenance_expense = assumptions.maintenance_per_inforce_year * beginning_inforce

    if policy_year == 1:
        acquisition_expense = assumptions.acquisition_fixed_expense
        premium_related_expense = assumptions.acquisition_pct_first_year_premium * expected_premium
    else:
        acquisition_expense = 0.0
        premium_related_expense = assumptions.renewal_pct_premium * expected_premium

    return acquisition_expense, maintenance_expense, premium_related_expense


def build_policy_cash_flows(
    assumptions: ProjectAssumptions,
    projection: list[PolicyYearProjection],
    annual_premium: float,
) -> list[PolicyYearCashFlow]:
    """Attach premium, expenses, and net cash flow to a Loop 2 projection."""

    if annual_premium < 0:
        raise CashFlowError("annual_premium cannot be negative.")
    if not projection:
        raise CashFlowError("projection must contain at least one policy year.")

    records: list[PolicyYearCashFlow] = []

    for row in projection:
        expected_premium = row.beginning_inforce_probability * annual_premium
        acquisition_expense, maintenance_expense, premium_related_expense = year_expenses(
            assumptions, row.policy_year, row.beginning_inforce_probability, expected_premium
        )
        total_expense = acquisition_expense + maintenance_expense + premium_related_expense
        net_cash_flow = expected_premium - row.expected_death_benefit - total_expense
        present_value_net_cash_flow = row.discount_factor * net_cash_flow

        records.append(
            PolicyYearCashFlow(
                policy_year=row.policy_year,
                attained_age=row.attained_age,
                beginning_inforce_probability=row.beginning_inforce_probability,
                mortality_rate_qx=row.mortality_rate_qx,
                lapse_rate=row.lapse_rate,
                death_probability=row.death_probability,
                lapse_probability=row.lapse_probability,
                ending_inforce_probability=row.ending_inforce_probability,
                discount_factor=row.discount_factor,
                expected_premium=expected_premium,
                expected_death_benefit=row.expected_death_benefit,
                acquisition_expense=acquisition_expense,
                maintenance_expense=maintenance_expense,
                premium_related_expense=premium_related_expense,
                net_cash_flow=net_cash_flow,
                present_value_net_cash_flow=present_value_net_cash_flow,
            )
        )

    return records


def summarize_policy(cash_flows: list[PolicyYearCashFlow]) -> PolicySummary:
    """Reduce a full cash-flow schedule to the policy-level summary metrics."""

    if not cash_flows:
        raise CashFlowError("cash_flows must contain at least one policy year.")

    pv_premiums = sum(r.discount_factor * r.expected_premium for r in cash_flows)
    pv_claims = sum(r.discount_factor * r.expected_death_benefit for r in cash_flows)
    pv_expenses = sum(
        r.discount_factor * (r.acquisition_expense + r.maintenance_expense + r.premium_related_expense)
        for r in cash_flows
    )
    pv_profit = sum(r.present_value_net_cash_flow for r in cash_flows)
    pv_profit_margin = pv_profit / pv_premiums if pv_premiums != 0 else float("nan")

    return PolicySummary(
        pv_premiums=pv_premiums,
        pv_claims=pv_claims,
        pv_expenses=pv_expenses,
        pv_profit=pv_profit,
        pv_profit_margin=pv_profit_margin,
    )
