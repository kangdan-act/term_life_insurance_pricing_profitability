# Life Insurance Pricing & Profitability Engine

A reproducible actuarial pricing project for a simplified U.S. 20-year level term life product.

## Project objective

For each synthetic applicant/policy, estimate expected mortality, lapse, claims, expenses,
premium requirements, present value of profit, and profit margin. Then aggregate results
to portfolio segments and stress key pricing assumptions.

## 12-loop development roadmap

1. **Specification & actuarial contract** — lock product, assumptions, inputs, outputs, validation gates.
2. **Core projection engine** — survival, mortality, lapse, in-force and discounting.
3. **Mortality data layer** — import/calibrate public mortality table data.
4. **Synthetic portfolio generator** — create realistic applicant/policy records.
5. **Gross premium engine** — solve premiums for target profitability.
6. **Expense & commission engine** — acquisition, maintenance, percentage-of-premium expenses.
7. **Profitability engine** — annual cash flows, PV profit, margin, IRR-style metrics.
8. **Experience analytics** — A/E mortality and lapse by segment/duration.
9. **Scenario & sensitivity engine** — mortality, lapse, interest, expenses, premium stresses.
10. **Statistical challenger** — interpretable mortality/lapse model vs actuarial baseline.
11. **Visualization & executive outputs** — portfolio diagnostics, pricing curves, scenario charts.
12. **Audit, refactor & GitHub release** — reproducibility, tests, documentation, model limitations.

## Status: all 12 loops complete

All twelve roadmap loops have a working implementation and test coverage under `tests/`
(TEST_SPEC.md Gates A-E). Loop 12 itself (this section, `LICENSE`, `MODEL_LIMITATIONS.md`) is the
audit/refactor/release pass.

| Loop | Module(s) |
|---|---|
| 1. Spec & actuarial contract | `PROJECT_SPEC.md`, `ACTUARIAL_ASSUMPTIONS.md`, `TEST_SPEC.md`, `config/assumptions.yaml`, `src/life_pricing/config.py` |
| 2. Core projection engine | `src/life_pricing/projection.py` |
| 3. Mortality data layer | `src/life_pricing/mortality.py` |
| 4. Synthetic portfolio generator | `src/life_pricing/portfolio.py` |
| 5. Gross premium engine | `src/life_pricing/premium.py` |
| 6. Expense & commission engine | `src/life_pricing/cashflow.py` (`year_expenses`) |
| 7. Profitability engine | `src/life_pricing/cashflow.py` (`build_policy_cash_flows`, `summarize_policy`) |
| 8. Experience analytics (A/E) | `src/life_pricing/experience.py` |
| 9. Scenario & sensitivity engine | `src/life_pricing/scenario.py` |
| 10. Statistical challenger | `src/life_pricing/challenger.py` |
| 11. Visualization & executive outputs | `src/life_pricing/visualization.py`, `scripts/generate_executive_report.py` |
| 12. Audit, refactor & GitHub release | This README section, `LICENSE`, `MODEL_LIMITATIONS.md` |

## V1.1 rigor pass (post-Loop-12)

Three corrections/additions made after the initial 12-loop release, each documented in full in
`ACTUARIAL_ASSUMPTIONS.md`:

1. **Cash-flow timing fix.** Premiums (beginning of year) and claims (end of year) were both
   being discounted with the same `v_t = (1+i)^-t`, silently deferring the beginning-of-year
   premium and issue-date acquisition expense by a year. Now uses three component-specific
   discount factors -- see "Cash-flow timing (V1.1)" in `ACTUARIAL_ASSUMPTIONS.md`.
2. **A/E lapse denominator fix.** The expected-lapse exposure used the raw table lapse rate
   `l_t` instead of the competing-decrement-consistent `(1 - q_t) * l_t`, understating A/E lapse
   relative to how the simulation itself samples lapse events -- see "Experience simulation
   basis" in `ACTUARIAL_ASSUMPTIONS.md`.
3. **Portfolio-wide pricing** (`src/life_pricing/portfolio_pricing.py`, new). Implements
   `PROJECT_SPEC.md` section 6, which had been specified since Loop 1 but never built: prices all
   10,000 policies (not just the representative policy), distinguishes `indicated_premium`
   (individually solved) from `book_premium` (rate-cell-banded, what is actually charged), and
   reports profitability by age band, sex, smoker status, underwriting class, face amount band,
   distribution channel, and issue cohort -- see "Portfolio pricing (V1.1)" in
   `ACTUARIAL_ASSUMPTIONS.md` and `tests/test_portfolio_pricing.py`.

## Run (fresh environment)

**Step 0 -- get the raw mortality data.** `data/raw/` is intentionally *not* committed to git
(see `.gitignore`) because it holds a third-party data export. Before running tests or the
engine, download the SOA 2015 VBT Smoker Distinct select-and-ultimate tables from
[mort.soa.org](https://mort.soa.org) (Table Identity 3265 family: Male/Female x Smoker/Non-Smoker,
Age Nearest Birthday) as `.xls` and place them at exactly:

```
data/raw/Non_Smoker_Female.xls
data/raw/Non_Smoker_Male.xls
data/raw/Smoke_Female.xls      # female smoker
data/raw/Smoker_Male.xls
```

See `docs/DATA_SOURCES.md` for the full provenance note (including why this project ended up on
2015 VBT rather than the 2017 CSO originally targeted in Loop 1).

**Then:**

```bash
python -m pip install -r requirements.txt
pytest -q                                          # full test suite (Gates A-E)
PYTHONPATH=src python3 scripts/generate_executive_report.py  # end-to-end run + charts + full-portfolio pricing
```

The report script now also prices the full synthetic portfolio (not just the representative
policy) and writes `data/processed/priced_portfolio.csv` and
`data/processed/portfolio_profitability_by_segment.csv` (see "V1.1 rigor pass" above).

No network access is required to run the test suite once `data/raw/` is populated and
dependencies are installed (TEST_SPEC.md Gate E).

## Current v1 product

- Product: 20-year level term life
- Issue ages: 25–60
- Premium mode: annual, beginning of policy year (V1.1: premiums now discount at
  `(1+i)^-(t-1)`, matching this stated timing -- see "V1.1 rigor pass" above)
- Benefit timing: end of year of death (discounted at `(1+i)^-t`, unchanged)
- Mortality basis: SOA 2015 VBT Smoker Distinct select-and-ultimate tables, by sex and smoker
  status, with an underwriting-class multiplier layered on top (corrected from the 2017 CSO
  originally targeted in Loop 1 -- see `docs/DATA_SOURCES.md`). As of Loop 12, the
  underwriting-class multiplier is derived from real SOA ILEC 2012-2019 Mortality Experience
  Report A/E data, claims-weighted and face-amount-band-specific (Loop 12b) rather than a flat
  arbitrary guess -- see `docs/DATA_SOURCES.md`.
- Portfolio data: synthetic applicant/policy data (Loop 4); Loop 8's "actual" experience is a
  labeled simulation against a second, separately declared basis -- as of Loop 12/12b both its
  mortality curve (ILEC-derived) and its lapse curve (derived from a by-risk-class cut of the
  2009-13 Persistency Update) are real, duration-varying data rather than arbitrary scalars,
  though neither is a fully independent experience dataset from what the pricing basis already
  uses -- see `ACTUARIAL_ASSUMPTIONS.md`
- Lapse: duration-based assumption; as of Loop 12 this is the real SOA "2009-13 US Individual
  Life Persistency Update" 20-Year level term lapse curve, including the real end-of-level-period
  shock lapse -- see `docs/DATA_SOURCES.md`
- Interest rate: 5.16% annual effective, the real 20-Year Treasury Constant Maturity yield (FRED
  DGS20) as of 2026-08-25 -- replacing an arbitrary illustrative 4.0% (Loop 12) -- see
  `docs/DATA_SOURCES.md`
- Pricing target: solve for a target PV profit margin (closed-form; see `src/life_pricing/premium.py`)

## Known limitations

See `MODEL_LIMITATIONS.md` for the full list (mortality-basis correction, the underwriting-class
relativity and lapse table's real-data provenance and remaining approximations, simulated rather
than fully-real experience data, and everything listed as out of scope in `PROJECT_SPEC.md`
section 9).
