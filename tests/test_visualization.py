from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import pandas as pd
import pytest

from life_pricing.config import load_assumptions
from life_pricing.experience import actual_to_expected_by_segment, simulate_policy_exposures
from life_pricing.portfolio import generate_synthetic_portfolio
from life_pricing.projection import project_policy
from life_pricing.mortality import mortality_curve_for_policy
from life_pricing.scenario import run_interest_rate_sensitivity
from life_pricing.visualization import (
    VisualizationError,
    plot_ae_by_segment,
    plot_inforce_decrement_curve,
    plot_portfolio_composition,
    plot_sensitivity_curve,
    save_figure,
)

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "assumptions.yaml"

matplotlib.use("Agg")


@pytest.fixture(scope="module")
def assumptions():
    return load_assumptions(CONFIG_PATH)


@pytest.fixture(scope="module")
def projection_df(assumptions):
    qx = mortality_curve_for_policy(assumptions, issue_age=40, sex="male", smoker_status="nonsmoker", underwriting_class="Standard")
    records = project_policy(assumptions, issue_age=40, mortality_rates_qx=qx, face_amount=300_000)
    return pd.DataFrame([r.__dict__ for r in records])


@pytest.fixture(scope="module")
def portfolio_and_segments(assumptions):
    portfolio = generate_synthetic_portfolio(assumptions, n_policies=1500, random_seed=31)
    exposures = simulate_policy_exposures(assumptions, portfolio, random_seed=31)
    segment_df = actual_to_expected_by_segment(exposures, portfolio, segment_columns=["sex", "smoker_status"])
    return portfolio, segment_df


def test_plot_sensitivity_curve_returns_figure(assumptions):
    scenario_df = run_interest_rate_sensitivity(
        assumptions, issue_age=40, sex="male", smoker_status="nonsmoker", underwriting_class="Standard", face_amount=300_000
    )
    fig = plot_sensitivity_curve(scenario_df, "annual_effective_rate", "Interest rate sensitivity", "Annual effective rate")
    assert isinstance(fig, plt.Figure)
    plt.close(fig)


def test_plot_sensitivity_curve_missing_columns_raises():
    with pytest.raises(VisualizationError):
        plot_sensitivity_curve(pd.DataFrame({"x": [1, 2]}), "x", "title", "x label")


def test_plot_sensitivity_curve_empty_df_raises():
    with pytest.raises(VisualizationError):
        plot_sensitivity_curve(
            pd.DataFrame(columns=["annual_effective_rate", "annual_premium", "pv_profit_margin"]),
            "annual_effective_rate", "title", "x label",
        )


def test_plot_inforce_decrement_curve_returns_figure(projection_df):
    fig = plot_inforce_decrement_curve(projection_df)
    assert isinstance(fig, plt.Figure)
    plt.close(fig)


def test_plot_inforce_decrement_curve_missing_columns_raises():
    with pytest.raises(VisualizationError):
        plot_inforce_decrement_curve(pd.DataFrame({"policy_year": [1, 2]}))


def test_plot_ae_by_segment_returns_figure(portfolio_and_segments):
    _, segment_df = portfolio_and_segments
    fig = plot_ae_by_segment(segment_df, "sex", metric="ae_mortality")
    assert isinstance(fig, plt.Figure)
    plt.close(fig)


def test_plot_ae_by_segment_unknown_column_raises(portfolio_and_segments):
    _, segment_df = portfolio_and_segments
    with pytest.raises(VisualizationError):
        plot_ae_by_segment(segment_df, "not_a_column")


def test_plot_portfolio_composition_returns_figure(portfolio_and_segments):
    portfolio, _ = portfolio_and_segments
    fig = plot_portfolio_composition(portfolio, "underwriting_class")
    assert isinstance(fig, plt.Figure)
    plt.close(fig)


def test_plot_portfolio_composition_unknown_column_raises(portfolio_and_segments):
    portfolio, _ = portfolio_and_segments
    with pytest.raises(VisualizationError):
        plot_portfolio_composition(portfolio, "not_a_column")


def test_save_figure_writes_a_file(projection_df, tmp_path):
    fig = plot_inforce_decrement_curve(projection_df)
    path = save_figure(fig, "test_inforce_curve.png", output_dir=tmp_path)
    plt.close(fig)
    assert path.exists()
    assert path.stat().st_size > 0
