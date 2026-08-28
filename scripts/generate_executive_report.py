#!/usr/bin/env python3
"""Reproducible end-to-end run: assumptions -> mortality -> portfolio ->
pricing -> experience -> scenarios -> challenger -> charts.

This script contains no unique business logic of its own (AGENTS.md) -- it
only calls the tested functions in src/life_pricing/ and writes their
outputs to data/processed/ and reports/figures/. Run it from the project
root:

    PYTHONPATH=src python3 scripts/generate_executive_report.py
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from life_pricing.cashflow import build_policy_cash_flows, summarize_policy
from life_pricing.challenger import fit_challenger
from life_pricing.config import load_assumptions
from life_pricing.experience import (
    actual_to_expected_by_segment,
    overall_actual_to_expected,
    simulate_policy_exposures,
)
from life_pricing.mortality import mortality_curve_for_policy, write_processed_tables
from life_pricing.portfolio import generate_synthetic_portfolio
from life_pricing.premium import solve_annual_premium
from life_pricing.projection import project_policy
from life_pricing.scenario import run_full_sensitivity_grid
from life_pricing.visualization import (
    plot_ae_by_segment,
    plot_inforce_decrement_curve,
    plot_portfolio_composition,
    plot_sensitivity_curve,
    save_figure,
)

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "assumptions.yaml"

REPRESENTATIVE_POLICY = dict(
    issue_age=40, sex="male", smoker_status="nonsmoker", underwriting_class="Standard", face_amount=300_000
)


def main() -> None:
    assumptions = load_assumptions(CONFIG_PATH)
    print(f"Loaded assumptions: {assumptions.mortality_reference_basis}")

    # Loop 3: refresh the processed mortality CSVs from the raw SOA tables.
    processed_paths = write_processed_tables()
    print(f"Wrote {len(processed_paths)} processed mortality files.")

    # Loops 2 + 5-7: price the representative policy.
    # (mortality_curve_for_policy now accepts face_amount directly -- Loop
    # 12b's underwriting-class relativity varies by face-amount band.)
    qx = mortality_curve_for_policy(assumptions, **REPRESENTATIVE_POLICY)
    projection = project_policy(
        assumptions,
        issue_age=REPRESENTATIVE_POLICY["issue_age"],
        mortality_rates_qx=qx,
        face_amount=REPRESENTATIVE_POLICY["face_amount"],
    )
    premium = solve_annual_premium(assumptions, projection)
    cash_flows = build_policy_cash_flows(assumptions, projection, premium)
    summary = summarize_policy(cash_flows)
    print(
        f"Representative policy ({REPRESENTATIVE_POLICY}): "
        f"annual premium=${premium:,.2f}, PV profit margin={summary.pv_profit_margin:.4f}"
    )

    # Loop 4: synthetic portfolio.
    portfolio = generate_synthetic_portfolio(assumptions)
    print(f"Generated synthetic portfolio: {len(portfolio)} policies.")

    # Loop 8: experience simulation + A/E.
    exposures = simulate_policy_exposures(assumptions, portfolio)
    overall_ae = overall_actual_to_expected(exposures)
    print(f"Overall A/E: mortality={overall_ae['ae_mortality']:.3f}, lapse={overall_ae['ae_lapse']:.3f}")
    segment_ae = actual_to_expected_by_segment(exposures, portfolio, segment_columns=["sex", "smoker_status"])

    # Loop 9: scenario grids.
    grids = run_full_sensitivity_grid(assumptions, **REPRESENTATIVE_POLICY)

    # Loop 10: statistical challenger.
    challenger = fit_challenger(exposures, portfolio, outcome="death")
    print(
        f"Mortality challenger vs baseline (held-out log-loss): "
        f"baseline={challenger.baseline_log_loss:.5f}, challenger={challenger.challenger_log_loss:.5f}"
    )

    # Loop 11: charts.
    figures = {
        "inforce_decrement_curve.png": plot_inforce_decrement_curve(
            pd.DataFrame([r.__dict__ for r in projection])
        ),
        "interest_rate_sensitivity.png": plot_sensitivity_curve(
            grids["interest_rate"], "annual_effective_rate", "Interest rate sensitivity", "Annual effective rate"
        ),
        "mortality_stress_sensitivity.png": plot_sensitivity_curve(
            grids["mortality_stress"], "mortality_stress_multiplier", "Mortality stress sensitivity", "Mortality stress multiplier"
        ),
        "lapse_stress_sensitivity.png": plot_sensitivity_curve(
            grids["lapse_stress"], "lapse_multiplier", "Lapse stress sensitivity", "Lapse multiplier"
        ),
        "profit_margin_sensitivity.png": plot_sensitivity_curve(
            grids["profit_margin"], "target_profit_margin", "Profit margin sensitivity", "Target PV profit margin"
        ),
        "ae_mortality_by_sex.png": plot_ae_by_segment(segment_ae, "sex", metric="ae_mortality"),
        "portfolio_by_underwriting_class.png": plot_portfolio_composition(portfolio, "underwriting_class"),
    }

    for filename, fig in figures.items():
        path = save_figure(fig, filename)
        plt.close(fig)
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()
