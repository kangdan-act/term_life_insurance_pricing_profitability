"""Visualization & executive outputs (Loop 11).

Turns the outputs of earlier loops (Loop 2 projections, Loop 9 scenario
grids, Loop 8 experience A/E tables, Loop 4 portfolios) into matplotlib
figures for pricing review and executive/GitHub-README use. Every function
here returns a `matplotlib.figure.Figure` rather than calling `plt.show()`
or writing a file itself, so callers (notebooks, scripts, tests) decide
whether and where to save it. No calculation logic lives in this module --
it only plots numbers produced by the earlier loops (AGENTS.md: "no
notebook may contain unique business logic", and by the same principle,
no plotting module should either).
"""

from __future__ import annotations

from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import pandas as pd

matplotlib.use("Agg")  # headless-safe backend; callers can still savefig()

REPORTS_FIGURES_DIR = Path(__file__).resolve().parents[2] / "reports" / "figures"

_STYLE = {
    "figure.facecolor": "white",
    "axes.facecolor": "white",
    "axes.edgecolor": "#444444",
    "axes.grid": True,
    "grid.color": "#dddddd",
    "grid.linewidth": 0.6,
    "font.size": 10,
}


class VisualizationError(ValueError):
    """Raised when a plotting function is given data it cannot render."""


def save_figure(fig: plt.Figure, filename: str, output_dir: Path = REPORTS_FIGURES_DIR) -> Path:
    """Save a figure to reports/figures/ (or another directory) and return the path."""

    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / filename
    fig.savefig(path, dpi=150, bbox_inches="tight")
    return path


def plot_sensitivity_curve(
    scenario_df: pd.DataFrame,
    x_column: str,
    title: str,
    x_label: str,
) -> plt.Figure:
    """Generic two-panel sensitivity chart: annual premium and PV profit
    margin against one scenario input column (e.g. interest rate, mortality
    stress multiplier). Used for all four Loop 9 sensitivity grids."""

    required = {x_column, "annual_premium", "pv_profit_margin"}
    missing = required - set(scenario_df.columns)
    if missing:
        raise VisualizationError(f"scenario_df is missing required column(s): {sorted(missing)}")
    if scenario_df.empty:
        raise VisualizationError("scenario_df must contain at least one row.")

    with plt.rc_context(_STYLE):
        fig, (ax_premium, ax_margin) = plt.subplots(1, 2, figsize=(10, 4))
        data = scenario_df.sort_values(x_column)

        ax_premium.plot(data[x_column], data["annual_premium"], marker="o", color="#2a6f97")
        ax_premium.set_title("Indicated annual premium")
        ax_premium.set_xlabel(x_label)
        ax_premium.set_ylabel("Annual premium ($)")

        ax_margin.plot(data[x_column], data["pv_profit_margin"], marker="o", color="#bb3e03")
        ax_margin.set_title("PV profit margin")
        ax_margin.set_xlabel(x_label)
        ax_margin.set_ylabel("PV profit margin")

        fig.suptitle(title)
        fig.tight_layout()

    return fig


def plot_inforce_decrement_curve(projection_df: pd.DataFrame) -> plt.Figure:
    """Stacked view of in-force decay: beginning in-force, split into what
    exits to death vs lapse vs stays in force, by policy year."""

    required = {"policy_year", "beginning_inforce_probability", "death_probability", "lapse_probability"}
    missing = required - set(projection_df.columns)
    if missing:
        raise VisualizationError(f"projection_df is missing required column(s): {sorted(missing)}")
    if projection_df.empty:
        raise VisualizationError("projection_df must contain at least one row.")

    data = projection_df.sort_values("policy_year")

    with plt.rc_context(_STYLE):
        fig, ax = plt.subplots(figsize=(8, 4.5))
        ax.plot(
            data["policy_year"], data["beginning_inforce_probability"],
            label="Beginning in-force", color="#264653", linewidth=2,
        )
        ax.fill_between(
            data["policy_year"], 0, data["death_probability"],
            label="Death decrement", color="#e76f51", alpha=0.6,
        )
        ax.fill_between(
            data["policy_year"], data["death_probability"],
            data["death_probability"] + data["lapse_probability"],
            label="Lapse decrement", color="#e9c46a", alpha=0.6,
        )
        ax.set_xlabel("Policy year")
        ax.set_ylabel("Probability")
        ax.set_title("In-force decrement curve")
        ax.legend(loc="upper right")
        fig.tight_layout()

    return fig


def plot_ae_by_segment(
    segment_df: pd.DataFrame,
    segment_column: str,
    metric: str = "ae_mortality",
    top_n: int | None = None,
) -> plt.Figure:
    """Bar chart of an actual-to-expected ratio (Loop 8) across categories of
    one segment column, with a reference line at A/E = 1.0."""

    if segment_column not in segment_df.columns:
        raise VisualizationError(f"segment_df has no column {segment_column!r}.")
    if metric not in segment_df.columns:
        raise VisualizationError(f"segment_df has no column {metric!r}.")
    if segment_df.empty:
        raise VisualizationError("segment_df must contain at least one row.")

    grouped = segment_df.groupby(segment_column)[metric].mean().sort_values(ascending=False)
    if top_n is not None:
        grouped = grouped.head(top_n)

    with plt.rc_context(_STYLE):
        fig, ax = plt.subplots(figsize=(8, max(3, 0.4 * len(grouped))))
        colors = ["#e76f51" if v > 1.0 else "#2a9d8f" for v in grouped.values]
        ax.barh(grouped.index.astype(str), grouped.values, color=colors)
        ax.axvline(1.0, color="#444444", linestyle="--", linewidth=1)
        ax.set_xlabel(metric)
        ax.set_title(f"{metric} by {segment_column}")
        fig.tight_layout()

    return fig


def plot_portfolio_composition(portfolio_df: pd.DataFrame, column: str) -> plt.Figure:
    """Bar chart of synthetic portfolio composition (policy count) by one
    categorical column (Loop 4 output)."""

    if column not in portfolio_df.columns:
        raise VisualizationError(f"portfolio_df has no column {column!r}.")
    if portfolio_df.empty:
        raise VisualizationError("portfolio_df must contain at least one row.")

    counts = portfolio_df[column].value_counts().sort_index()

    with plt.rc_context(_STYLE):
        fig, ax = plt.subplots(figsize=(7, 4))
        ax.bar(counts.index.astype(str), counts.values, color="#2a6f97")
        ax.set_xlabel(column)
        ax.set_ylabel("Policy count")
        ax.set_title(f"Synthetic portfolio composition: {column}")
        ax.tick_params(axis="x", rotation=30)
        fig.tight_layout()

    return fig
