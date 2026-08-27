"""Scenario & sensitivity engine (Loop 9).

Runs the full pricing pipeline (mortality -> projection -> premium solve ->
cash flow -> summary) across a grid of assumption overrides, matching the
sensitivity ranges ACTUARIAL_ASSUMPTIONS.md already commits to (interest:
2/3/4/5/6%; profit margin: 0/5/10/15%) plus mortality and lapse stress
grids.

Every scenario runs against a deep copy of the base assumptions' raw dict
-- `apply_scenario()` never mutates `base_assumptions` itself, per
AGENTS.md's review question "Does any scenario unintentionally mutate the
base configuration?".
"""

from __future__ import annotations

from copy import deepcopy
from typing import Callable

import pandas as pd

from life_pricing.cashflow import build_policy_cash_flows, summarize_policy
from life_pricing.config import ProjectAssumptions
from life_pricing.mortality import mortality_curve_for_policy
from life_pricing.premium import solve_annual_premium
from life_pricing.projection import project_policy

INTEREST_RATE_SCENARIOS = [0.02, 0.03, 0.04, 0.05, 0.06]
PROFIT_MARGIN_SCENARIOS = [0.0, 0.05, 0.10, 0.15]
MORTALITY_STRESS_SCENARIOS = [0.75, 1.0, 1.25, 1.5, 2.0]
LAPSE_STRESS_SCENARIOS = [0.5, 0.75, 1.0, 1.25, 1.5]


class ScenarioError(ValueError):
    """Raised when scenario construction or execution inputs are invalid."""


def apply_scenario(
    base_assumptions: ProjectAssumptions, mutate: Callable[[dict], None]
) -> ProjectAssumptions:
    """Return a NEW ProjectAssumptions with `mutate` applied to a deep copy
    of the base raw dict. `base_assumptions` (and its underlying raw dict)
    is never modified."""

    raw_copy = deepcopy(base_assumptions.raw)
    mutate(raw_copy)
    return ProjectAssumptions(raw=raw_copy)


def _with_interest_rate(rate: float) -> Callable[[dict], None]:
    def mutate(raw: dict) -> None:
        raw["interest"]["annual_effective_rate"] = rate

    return mutate


def _with_mortality_stress(multiplier: float) -> Callable[[dict], None]:
    def mutate(raw: dict) -> None:
        raw["mortality"]["stress_multiplier"] = multiplier

    return mutate


def _with_lapse_multiplier(multiplier: float) -> Callable[[dict], None]:
    def mutate(raw: dict) -> None:
        raw["lapse"]["by_duration"] = {
            duration: min(max(rate * multiplier, 0.0), 1.0)
            for duration, rate in raw["lapse"]["by_duration"].items()
        }

    return mutate


def price_policy_under_assumptions(
    assumptions: ProjectAssumptions,
    issue_age: int,
    sex: str,
    smoker_status: str,
    underwriting_class: str,
    face_amount: float,
    target_margin: float | None = None,
) -> dict[str, float]:
    """Run the full Loop 2-7 pipeline for one policy under one assumption set."""

    qx = mortality_curve_for_policy(
        assumptions,
        issue_age=issue_age,
        sex=sex,
        smoker_status=smoker_status,
        underwriting_class=underwriting_class,
    )
    projection = project_policy(assumptions, issue_age=issue_age, mortality_rates_qx=qx, face_amount=face_amount)
    premium = solve_annual_premium(assumptions, projection, target_margin=target_margin)
    cash_flows = build_policy_cash_flows(assumptions, projection, premium)
    summary = summarize_policy(cash_flows)

    return {
        "annual_premium": premium,
        "pv_premiums": summary.pv_premiums,
        "pv_claims": summary.pv_claims,
        "pv_expenses": summary.pv_expenses,
        "pv_profit": summary.pv_profit,
        "pv_profit_margin": summary.pv_profit_margin,
    }


def run_interest_rate_sensitivity(
    base_assumptions: ProjectAssumptions,
    issue_age: int,
    sex: str,
    smoker_status: str,
    underwriting_class: str,
    face_amount: float,
    rates: list[float] | None = None,
) -> pd.DataFrame:
    rows = []
    for rate in rates if rates is not None else INTEREST_RATE_SCENARIOS:
        scenario_assumptions = apply_scenario(base_assumptions, _with_interest_rate(rate))
        result = price_policy_under_assumptions(
            scenario_assumptions, issue_age, sex, smoker_status, underwriting_class, face_amount
        )
        rows.append({"annual_effective_rate": rate, **result})
    return pd.DataFrame(rows)


def run_profit_margin_sensitivity(
    base_assumptions: ProjectAssumptions,
    issue_age: int,
    sex: str,
    smoker_status: str,
    underwriting_class: str,
    face_amount: float,
    margins: list[float] | None = None,
) -> pd.DataFrame:
    rows = []
    for margin in margins if margins is not None else PROFIT_MARGIN_SCENARIOS:
        result = price_policy_under_assumptions(
            base_assumptions, issue_age, sex, smoker_status, underwriting_class, face_amount, target_margin=margin
        )
        rows.append({"target_profit_margin": margin, **result})
    return pd.DataFrame(rows)


def run_mortality_stress_sensitivity(
    base_assumptions: ProjectAssumptions,
    issue_age: int,
    sex: str,
    smoker_status: str,
    underwriting_class: str,
    face_amount: float,
    multipliers: list[float] | None = None,
) -> pd.DataFrame:
    rows = []
    for multiplier in multipliers if multipliers is not None else MORTALITY_STRESS_SCENARIOS:
        scenario_assumptions = apply_scenario(base_assumptions, _with_mortality_stress(multiplier))
        result = price_policy_under_assumptions(
            scenario_assumptions, issue_age, sex, smoker_status, underwriting_class, face_amount
        )
        rows.append({"mortality_stress_multiplier": multiplier, **result})
    return pd.DataFrame(rows)


def run_lapse_stress_sensitivity(
    base_assumptions: ProjectAssumptions,
    issue_age: int,
    sex: str,
    smoker_status: str,
    underwriting_class: str,
    face_amount: float,
    multipliers: list[float] | None = None,
) -> pd.DataFrame:
    rows = []
    for multiplier in multipliers if multipliers is not None else LAPSE_STRESS_SCENARIOS:
        scenario_assumptions = apply_scenario(base_assumptions, _with_lapse_multiplier(multiplier))
        result = price_policy_under_assumptions(
            scenario_assumptions, issue_age, sex, smoker_status, underwriting_class, face_amount
        )
        rows.append({"lapse_multiplier": multiplier, **result})
    return pd.DataFrame(rows)


def run_full_sensitivity_grid(
    base_assumptions: ProjectAssumptions,
    issue_age: int,
    sex: str,
    smoker_status: str,
    underwriting_class: str,
    face_amount: float,
) -> dict[str, pd.DataFrame]:
    """Convenience wrapper: run all four standard sensitivity grids at once."""

    return {
        "interest_rate": run_interest_rate_sensitivity(
            base_assumptions, issue_age, sex, smoker_status, underwriting_class, face_amount
        ),
        "profit_margin": run_profit_margin_sensitivity(
            base_assumptions, issue_age, sex, smoker_status, underwriting_class, face_amount
        ),
        "mortality_stress": run_mortality_stress_sensitivity(
            base_assumptions, issue_age, sex, smoker_status, underwriting_class, face_amount
        ),
        "lapse_stress": run_lapse_stress_sensitivity(
            base_assumptions, issue_age, sex, smoker_status, underwriting_class, face_amount
        ),
    }
