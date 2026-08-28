"""Portfolio-level pricing & profitability engine.

Implements PROJECT_SPEC.md section 6 ("Portfolio outputs"), which was
declared in the spec from Loop 1 onward but never actually built: every
other loop prices a single *representative* policy
(scripts/generate_executive_report.py's REPRESENTATIVE_POLICY), not the
full synthetic book. This module prices every policy in a portfolio and
rolls the results up by every section-6 dimension (issue age band, sex,
smoking status, underwriting class, face amount band, distribution
channel, issue cohort).

Two premiums are computed per policy, matching a distinction real pricing
actuaries deal with constantly:

- `indicated_premium`: the individually-solved actuarial premium for that
  exact policy's own characteristics (life_pricing.premium.solve_annual_premium
  applied one policy at a time) -- what the assumptions say this specific
  risk SHOULD cost, at full granularity.
- `book_premium`: the premium the policy is actually charged under a
  discretely-banded rate table -- one premium per (issue_age_band, sex,
  smoker_status, underwriting_class, face_amount_band) rating cell,
  computed once from that cell's average issue_age/face_amount and
  broadcast to every policy in the cell. Real filed rate manuals are
  coarser than a fully continuous "indicated" pricing model (administrable
  rate tables use discrete bands, not one rate per exact face amount), so
  book_premium models that same coarseness rather than assuming the whole
  book is priced perfectly. Both premiums target the SAME
  assumptions.target_profit_margin, so any indicated-vs-book gap reflects
  rate-table granularity alone, not a deliberate margin difference.

Realized per-policy profitability (pv_premiums/pv_claims/pv_expenses/
pv_profit/pv_profit_margin) is evaluated at book_premium -- the premium
actually collected -- which is what reveals over- and under-priced
segments: a policy whose book_premium is below its own indicated_premium
will show a realized pv_profit_margin below the target, and vice versa.
`indicated_pv_profit_margin` is also reported per policy as a sanity
check (it should equal assumptions.target_profit_margin by construction,
since indicated_premium is solved to hit exactly that margin).

This module never invents a new pricing formula -- every premium and cash
flow number here is produced by the same life_pricing.mortality /
life_pricing.projection / life_pricing.premium / life_pricing.cashflow
functions every other loop uses, just run once per policy (or once per
rate cell) instead of once for a single representative policy.
"""

from __future__ import annotations

import pandas as pd

from life_pricing.cashflow import build_policy_cash_flows, summarize_policy
from life_pricing.config import ProjectAssumptions
from life_pricing.experience import (
    actual_to_expected_by_segment,
    face_amount_band,
    issue_age_band,
)
from life_pricing.mortality import mortality_curve_for_policy
from life_pricing.premium import solve_annual_premium
from life_pricing.projection import project_policy

RATE_CELL_COLUMNS = [
    "issue_age_band",
    "sex",
    "smoker_status",
    "underwriting_class",
    "face_amount_band",
]

SEGMENT_COLUMNS = [
    "issue_age_band",
    "sex",
    "smoker_status",
    "underwriting_class",
    "face_amount_band",
    "distribution_channel",
    "issue_cohort",
]

PRICED_POLICY_COLUMNS = [
    "policy_id",
    "issue_age",
    "sex",
    "smoker_status",
    "underwriting_class",
    "face_amount",
    "issue_year",
    "distribution_channel",
    "state_region",
    "issue_age_band",
    "face_amount_band",
    "issue_cohort",
    "indicated_premium",
    "book_premium",
    "pv_premiums",
    "pv_claims",
    "pv_expenses",
    "pv_profit",
    "pv_profit_margin",
    "indicated_pv_profit_margin",
]


class PortfolioPricingError(ValueError):
    """Raised when portfolio-wide pricing inputs are invalid."""


def _price_one_policy(
    assumptions: ProjectAssumptions,
    issue_age: int,
    sex: str,
    smoker_status: str,
    underwriting_class: str,
    face_amount: float,
) -> tuple[float, list]:
    """Run mortality -> projection -> premium solve for one policy.

    Returns (indicated_premium, projection) so callers that also need the
    projection (to build cash flows at a different premium) don't have to
    recompute the mortality curve a second time.
    """

    qx = mortality_curve_for_policy(
        assumptions,
        issue_age=issue_age,
        sex=sex,
        smoker_status=smoker_status,
        underwriting_class=underwriting_class,
        face_amount=face_amount,
    )
    projection = project_policy(assumptions, issue_age=issue_age, mortality_rates_qx=qx, face_amount=face_amount)
    indicated_premium = solve_annual_premium(assumptions, projection)
    return indicated_premium, projection


def _add_segment_columns(portfolio: pd.DataFrame) -> pd.DataFrame:
    portfolio = portfolio.copy()
    portfolio["issue_age_band"] = portfolio["issue_age"].apply(issue_age_band)
    portfolio["face_amount_band"] = portfolio["face_amount"].apply(face_amount_band)
    portfolio["issue_cohort"] = portfolio["issue_year"]
    return portfolio


def price_all_policies(assumptions: ProjectAssumptions, portfolio: pd.DataFrame) -> pd.DataFrame:
    """Solve the individually-indicated premium for every policy in `portfolio`.

    Returns the input portfolio (plus segment columns) with an
    `indicated_premium` column added. Mortality curves are cached by
    (issue_age, sex, smoker_status, underwriting_class, face_amount) --
    the same cache key life_pricing.experience uses -- so policies sharing
    a full risk profile only pay the mortality-table-lookup cost once.
    """

    if portfolio.empty:
        raise PortfolioPricingError("portfolio must contain at least one policy.")

    portfolio = _add_segment_columns(portfolio)

    cache: dict[tuple, float] = {}
    indicated_premiums = []
    for row in portfolio.itertuples(index=False):
        key = (row.issue_age, row.sex, row.smoker_status, row.underwriting_class, row.face_amount)
        if key not in cache:
            premium, _ = _price_one_policy(
                assumptions, row.issue_age, row.sex, row.smoker_status, row.underwriting_class, row.face_amount
            )
            cache[key] = premium
        indicated_premiums.append(cache[key])

    portfolio = portfolio.copy()
    portfolio["indicated_premium"] = indicated_premiums
    return portfolio


def build_rate_table(assumptions: ProjectAssumptions, priced_portfolio: pd.DataFrame) -> pd.DataFrame:
    """Derive one book (filed rate table) premium per rating cell.

    A rating cell is (issue_age_band, sex, smoker_status, underwriting_class,
    face_amount_band) -- RATE_CELL_COLUMNS. Each cell's premium is solved
    for a single synthetic "representative" policy using that cell's
    average issue_age and average face_amount (both drawn from the actual
    policies observed in the cell, so the rate table only reflects
    business actually written, matching how a filed table would be set
    from the book it is meant to cover). This is a deliberate
    simplification of a real rate manual (which uses fixed, pre-declared
    rating points rather than realized-book averages) chosen so the table
    is fully reproducible from `priced_portfolio` alone -- see
    docs/DATA_SOURCES.md / MODEL_LIMITATIONS.md.

    Requires `priced_portfolio` to already carry the segment columns (i.e.
    the output of `price_all_policies` or `_add_segment_columns`).
    """

    if priced_portfolio.empty:
        raise PortfolioPricingError("priced_portfolio must contain at least one policy.")

    cells = priced_portfolio.groupby(RATE_CELL_COLUMNS, observed=True).agg(
        representative_issue_age=("issue_age", "mean"),
        representative_face_amount=("face_amount", "mean"),
        cell_policy_count=("policy_id", "count"),
    )

    book_premiums = []
    for cell_key, cell_row in cells.iterrows():
        _, sex, smoker_status, underwriting_class, _ = cell_key
        representative_issue_age = int(round(cell_row["representative_issue_age"]))
        representative_issue_age = min(
            max(representative_issue_age, assumptions.issue_age_min), assumptions.issue_age_max
        )
        representative_face_amount = float(cell_row["representative_face_amount"])

        premium, _ = _price_one_policy(
            assumptions,
            representative_issue_age,
            sex,
            smoker_status,
            underwriting_class,
            representative_face_amount,
        )
        book_premiums.append(premium)

    cells = cells.reset_index()
    cells["book_premium"] = book_premiums
    return cells[RATE_CELL_COLUMNS + ["representative_issue_age", "representative_face_amount", "cell_policy_count", "book_premium"]]


def evaluate_portfolio_pricing(assumptions: ProjectAssumptions, portfolio: pd.DataFrame) -> pd.DataFrame:
    """Full per-policy pricing + realized-profitability table for a portfolio.

    For every policy: solves indicated_premium (full granularity), looks up
    book_premium (rate-cell granularity, via build_rate_table), then builds
    cash flows AT BOOK_PREMIUM -- the premium actually charged -- to report
    the realized pv_premiums/pv_claims/pv_expenses/pv_profit/
    pv_profit_margin. `indicated_pv_profit_margin` is also reported (cash
    flows built at indicated_premium) as a sanity check: it should equal
    assumptions.target_profit_margin for every policy, since
    indicated_premium is solved to hit exactly that margin.
    """

    priced = price_all_policies(assumptions, portfolio)
    rate_table = build_rate_table(assumptions, priced)
    priced = priced.merge(rate_table[RATE_CELL_COLUMNS + ["book_premium"]], on=RATE_CELL_COLUMNS, how="left")

    pv_premiums_list = []
    pv_claims_list = []
    pv_expenses_list = []
    pv_profit_list = []
    pv_profit_margin_list = []
    indicated_pv_profit_margin_list = []

    mortality_curve_cache: dict[tuple, list[float]] = {}

    for row in priced.itertuples(index=False):
        cache_key = (row.issue_age, row.sex, row.smoker_status, row.underwriting_class, row.face_amount)
        if cache_key not in mortality_curve_cache:
            mortality_curve_cache[cache_key] = mortality_curve_for_policy(
                assumptions,
                issue_age=row.issue_age,
                sex=row.sex,
                smoker_status=row.smoker_status,
                underwriting_class=row.underwriting_class,
                face_amount=row.face_amount,
            )
        qx = mortality_curve_cache[cache_key]
        projection = project_policy(assumptions, issue_age=row.issue_age, mortality_rates_qx=qx, face_amount=row.face_amount)

        book_cash_flows = build_policy_cash_flows(assumptions, projection, row.book_premium)
        book_summary = summarize_policy(book_cash_flows)

        indicated_cash_flows = build_policy_cash_flows(assumptions, projection, row.indicated_premium)
        indicated_summary = summarize_policy(indicated_cash_flows)

        pv_premiums_list.append(book_summary.pv_premiums)
        pv_claims_list.append(book_summary.pv_claims)
        pv_expenses_list.append(book_summary.pv_expenses)
        pv_profit_list.append(book_summary.pv_profit)
        pv_profit_margin_list.append(book_summary.pv_profit_margin)
        indicated_pv_profit_margin_list.append(indicated_summary.pv_profit_margin)

    priced = priced.copy()
    priced["pv_premiums"] = pv_premiums_list
    priced["pv_claims"] = pv_claims_list
    priced["pv_expenses"] = pv_expenses_list
    priced["pv_profit"] = pv_profit_list
    priced["pv_profit_margin"] = pv_profit_margin_list
    priced["indicated_pv_profit_margin"] = indicated_pv_profit_margin_list

    return priced[PRICED_POLICY_COLUMNS]


def portfolio_profitability_by_segment(
    assumptions: ProjectAssumptions,
    portfolio: pd.DataFrame,
    priced: pd.DataFrame | None = None,
    exposures: pd.DataFrame | None = None,
    segment_columns: list[str] | None = None,
) -> pd.DataFrame:
    """PROJECT_SPEC.md section 6 portfolio rollup: profitability (and,
    when `exposures` is supplied, A/E ratios) by issue age band, sex,
    smoking status, underwriting class, face amount band, distribution
    channel, and issue cohort (or a caller-chosen subset/superset of those
    dimensions via `segment_columns`).

    `priced` is the output of `evaluate_portfolio_pricing`; if omitted it
    is computed from `portfolio` (an expensive step for the full 10,000-
    policy book -- pass a precomputed `priced` when calling this more than
    once against the same portfolio, e.g. for several different
    `segment_columns` breakdowns).

    `exposures` is the output of life_pricing.experience.simulate_policy_exposures;
    if supplied, `ae_mortality` and `ae_lapse` columns (per
    life_pricing.experience.actual_to_expected_by_segment) are merged in
    on the same segment columns, giving the single combined
    pricing-and-experience table PROJECT_SPEC.md section 6 calls for.
    """

    if priced is None:
        priced = evaluate_portfolio_pricing(assumptions, portfolio)

    if priced.empty:
        raise PortfolioPricingError("priced must contain at least one policy.")

    columns = segment_columns if segment_columns is not None else SEGMENT_COLUMNS
    unknown_columns = set(columns) - set(priced.columns)
    if unknown_columns:
        raise PortfolioPricingError(f"Unknown segment column(s): {sorted(unknown_columns)}")

    grouped = (
        priced.groupby(columns, observed=True)
        .agg(
            policy_count=("policy_id", "count"),
            total_face_amount=("face_amount", "sum"),
            avg_face_amount=("face_amount", "mean"),
            avg_indicated_premium=("indicated_premium", "mean"),
            avg_book_premium=("book_premium", "mean"),
            total_pv_premiums=("pv_premiums", "sum"),
            total_pv_claims=("pv_claims", "sum"),
            total_pv_expenses=("pv_expenses", "sum"),
            total_pv_profit=("pv_profit", "sum"),
        )
        .reset_index()
    )
    grouped["pv_profit_margin"] = grouped["total_pv_profit"] / grouped["total_pv_premiums"]
    grouped["book_vs_indicated_premium_ratio"] = grouped["avg_book_premium"] / grouped["avg_indicated_premium"]

    if exposures is not None:
        ae = actual_to_expected_by_segment(exposures, portfolio, segment_columns=columns)
        grouped = grouped.merge(ae[columns + ["ae_mortality", "ae_lapse"]], on=columns, how="left")

    return grouped
