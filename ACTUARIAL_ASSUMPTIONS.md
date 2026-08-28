# Actuarial Assumptions — V1

These assumptions are intentionally transparent and simplified. They are modeling assumptions,
not company pricing recommendations.

## Mortality

Reference basis (corrected in Loop 3 to match the actual source data -- see below):
- SOA 2015 VBT Smoker Distinct select-and-ultimate tables (mort.soa.org, Table Identity 3265
  family), one table per sex x smoker-status cell: Non_Smoker_Female, Non_Smoker_Male,
  Smoke_Female (smoker), Smoker_Male.
- Each table has a select period of 25 durations (rows = issue age 18-95, columns = duration
  1-25) and an ultimate table indexed by attained age (18-120). Because the V1 product's term
  (20 years) is shorter than the 25-duration select period, every policy-year rate for V1 comes
  from the select table; the ultimate fallback exists in code for future products with longer
  terms.
- Underwriting class (Preferred Plus / Preferred / Standard) is required by PROJECT_SPEC.md as a
  policy dimension, but the raw tables split by sex and smoker status only -- they do not encode
  underwriting class. A multiplicative underwriting-class relativity is applied on top of the base
  table (config/assumptions.yaml:
  `mortality.underwriting_class_multiplier_by_face_band`). **Updated in Loop 12** from V1
  illustrative guesses (flat 0.60/0.80/1.00) to values derived from real published data: the SOA
  "Individual Life Experience Committee (ILEC) 2012-2019 Mortality Experience Report" appendices,
  Appendix K1 (nonsmoker actual-to-2015-VBT-expected ratios by underwriting-class rank and
  face-amount band).

  **Loop 12b refinement**: rather than collapsing Appendix K1's face-amount detail into one flat
  multiplier per class, the relativity is now face-amount-band specific, since the raw data shows
  it genuinely varies by face amount (better classes separate further from Standard at lower face
  amounts):

  | Face amount band | Preferred Plus | Preferred | Standard |
  |---|---:|---:|---:|
  | $100,000-$249,999 | 0.6541 | 0.7588 | 1.0000 |
  | $250,000-$499,999 | 0.6433 | 0.7602 | 1.0000 |
  | $500,000-$1,000,000 | 0.6146 | 0.7182 | 1.0000 |

  Each band's figure is also claims-count-weighted across Appendix K1's duration-group columns
  (using the sheet's own "Number of Policy Claims" block as weights, a limited-fluctuation-style
  credibility weighting) rather than a simple average, so duration cells with more claims
  experience influence the relativity more than sparse ones. These are still not filed
  company-specific rates -- they are relativities implied by aggregate industry experience data --
  but they replace arbitrary guesses with a cited, reproducible, and now face-amount-aware source.
  See `docs/DATA_SOURCES.md` for the exact source cells and methodology.
- A mortality stress multiplier (config: mortality.stress_multiplier) is applied multiplicatively
  to q_x on top of the underwriting-class relativity, for sensitivity/scenario testing (Loop 9).

### Correction note (Loop 1 -> Loop 3)

The original Loop 1 draft of this document targeted "2017 CSO unloaded" as the mortality basis.
When Loop 3 parsed the actual files under `data/raw/`, they turned out to be the SOA 2015 VBT
Smoker Distinct tables instead. Per AGENTS.md ("do not silently alter assumptions to make tests
pass" / "explain any actuarial assumption introduced or changed"), this document and
`config/assumptions.yaml` were updated to accurately describe the data actually being used,
rather than keeping an incorrect "2017 CSO" label. See `docs/DATA_SOURCES.md` for the full
provenance discussion.

Why this basis:
2015 VBT is a public, insured-lives select-and-ultimate table published by the SOA specifically
for pricing/valuation use, split by sex and smoker status -- a reasonable and directly reproducible
free substitute for a licensed company-specific pricing table, consistent with this project's goal
of being fully reproducible on a normal development machine without paid data.

## Lapse

Base duration lapse assumption. **Updated in Loop 12**: this table was originally an illustrative
declining curve (8% -> 3%); it is now the real 20-Year level term lapse-rate-by-duration curve
from the SOA "2009-13 US Individual Life Persistency Update" report, sheet "Term -Part 1", the
"20-Year level term" Policy Lapse Rate block. See `docs/DATA_SOURCES.md` for the exact source
cells.

| Policy year | Annual lapse | Policy year | Annual lapse |
|---|---:|---|---:|
| 1 | 6.0% | 11 | 3.0% |
| 2 | 5.5% | 12 | 2.7% |
| 3 | 4.7% | 13 | 2.7% |
| 4 | 4.3% | 14 | 2.5% |
| 5 | 4.0% | 15 | 2.7% |
| 6 | 3.7% | 16 | 2.9% |
| 7 | 3.4% | 17 | 2.9% |
| 8 | 3.2% | 18 | 3.4% |
| 9 | 3.1% | 19 | 4.2% |
| 10 | 3.0% | 20 | **31.0%** |

Duration 20's 31.0% rate is the well-known "shock lapse" that occurs at the end of a level-term
product's level-premium period: premiums jump to attained-age (annually renewable term) rates at
the start of policy year 21, so most surviving, non-converting policyholders let the policy lapse
rather than pay the much higher renewal premium. This is a real, material feature of 20-year term
lapse experience, not an outlier to be smoothed away -- it now flows directly into the pricing
engine's premium solve and cash-flow projections (Loops 5-6) rather than being averaged out.

Lapse is modeled as a competing decrement after mortality within each annual period:
L_t = I_t * (1-q_t) * lapse_t

## Interest

Base annual effective discount rate: **5.16%**. **Updated in Loop 12** from an arbitrary
illustrative 4.0% to a real, publicly cited rate: the 20-Year Treasury Constant Maturity yield
(FRED series DGS20), 5.16% as of 2026-08-25 -- chosen for its ~20-year duration match to this
product's term, giving a defensible, citable anchor instead of a round-number guess. This is a
risk-free proxy, not a company's actual net investment income assumption; see
`MODEL_LIMITATIONS.md` for why that distinction matters, and `docs/DATA_SOURCES.md` for the
citation.

Sensitivity range planned (unchanged; `life_pricing.scenario`'s grid still spans a realistic band
around the base rate rather than being re-centered on 5.16% -- see `MODEL_LIMITATIONS.md`):
- 2%
- 3%
- 4%
- 5%
- 6%

## Expenses

V1 illustrative expense basis:

- Acquisition fixed expense: $150 per issued policy at issue
- Acquisition percent-of-premium expense: 25% of first-year premium
- Renewal premium expense: 5% of renewal premium
- Maintenance expense: $60 per in-force policy per year

## Profit target

Base target PV profit margin: **10% of PV premiums**

Additional scenario targets:
- 0% break-even
- 5%
- 10%
- 15%

## Cash-flow timing (V1.1)

**Corrected in V1.1.** PROJECT_SPEC.md section 2 has always specified "Premium mode: Annual,
beginning of policy year while in force" and "Benefit timing: End of policy year of death," but
Loop 1 through Loop 12's code applied a single discount factor `v_t = (1+i)^-t` to every cash-flow
component -- premiums, claims, and expenses alike. That silently treated the beginning-of-year
premium as if it were paid one full year later than the spec says, and treated the acquisition
expense (which is incurred at issue) the same way. This was internally consistent (every
component used the same `v_t`, so the identities held), but it was not what the spec's own
timing language describes, and it is exactly the kind of inconsistency a reviewing actuary would
flag (see AGENTS.md's review checklist: "Is benefit timing consistent with discount timing?").

V1.1 introduces three separate discount factors instead of one, matching each cash flow to its
own timing convention:

| Cash flow | Timing | Discount factor |
|---|---|---|
| Premium (`Prem_t`) | Beginning of policy year `t` | `v_b(t) = (1+i)^-(t-1)` |
| Death claim (`Claim_t`) | End of policy year `t` | `v_e(t) = (1+i)^-t` (unchanged) |
| Acquisition expense | At issue (year 1 only) | `v_b(1) = 1` (uses the premium factor) |
| Maintenance expense | Mid-year (deliberate choice, not specified elsewhere) | `v_m(t) = (1+i)^-(t-0.5)` |

Maintenance expense timing is not stated in PROJECT_SPEC.md, so mid-year was chosen deliberately
as a defensible middle ground (administrative/servicing costs are incurred continuously through
the year, not all at the start or all at the end) rather than defaulting it to match either the
premium or the claim timing. This is a new, explicitly declared modeling choice, not a hidden
one.

The premium closed-form (`life_pricing.premium.solve_annual_premium`) was re-derived under this
change, not just patched: the equation `P = B / (A - margin*C)` keeps the exact same shape,
because the derivation never depended on every component sharing one discount factor -- it only
required each `A`, `B`, `C` accumulator to use *a* consistent factor per component. `A` and `C`
(both premium-driven) now accumulate at `v_b(t)`; `B`'s claim term still uses `v_e(t)`; `B`'s
acquisition-expense term uses `v_b(1)` (i.e. undiscounted, matching an issue-date cash flow); and
`B`'s maintenance-expense term uses `v_m(t)`. All 178 pre-existing tests (including every
property-based Gate C premium test) pass unchanged under the new derivation, which is strong
evidence the algebra is correct and not just a plausible rewrite.

This produces a small but real economic difference from V1 through Loop 12: because premiums are
now valued as arriving one period earlier (undiscounted in year 1) and acquisition expense is no
longer artificially deferred a year, the indicated premium changes slightly relative to the old
single-factor model, and the year-by-year `present_value_net_cash_flow` figures are no longer
simply `discount_factor * net_cash_flow` -- they are the sum of three independently discounted
components (`present_value_premium + present_value_claim + present_value_expense`, each using its
own factor above).

## Portfolio pricing (V1.1)

PROJECT_SPEC.md section 6 ("Portfolio outputs") was declared from Loop 1 onward but never
implemented -- every prior loop only ever priced a single `REPRESENTATIVE_POLICY`
(`scripts/generate_executive_report.py`), not the full synthetic book. `life_pricing.portfolio_pricing`
(new in V1.1) closes that gap by pricing every policy in the 10,000-policy portfolio and rolling
the results up by every section-6 dimension (issue age band, sex, smoking status, underwriting
class, face amount band, distribution channel, issue cohort).

Two premiums are computed per policy, matching a distinction real pricing actuaries deal with
constantly:

- `indicated_premium`: the individually-solved actuarial premium for that exact policy's own
  characteristics (`life_pricing.premium.solve_annual_premium` applied one policy at a time) --
  what the assumptions say this specific risk should cost, at full granularity. By construction,
  every policy's `indicated_pv_profit_margin` equals `assumptions.target_profit_margin` exactly
  (currently 10%), since that is what the premium is solved to hit.
- `book_premium`: the premium the policy is actually charged under a discretely-banded rate table
  -- one premium per (issue_age_band, sex, smoker_status, underwriting_class, face_amount_band)
  rating cell, computed once from that cell's realized-portfolio average issue_age/face_amount and
  broadcast to every policy in the cell. Real filed rate manuals are coarser than a fully
  continuous "indicated" pricing model (administrable rate tables use discrete bands, not one rate
  per exact face amount), so `book_premium` models that same coarseness deliberately rather than
  assuming the whole book is priced perfectly.

Realized per-policy profitability (`pv_premiums`, `pv_claims`, `pv_expenses`, `pv_profit`,
`pv_profit_margin`) is evaluated at `book_premium` -- the premium actually collected -- which is
what reveals over- and under-priced segments: a policy whose `book_premium` sits below its own
`indicated_premium` shows a realized `pv_profit_margin` below target, and vice versa. Against the
full synthetic 10,000-policy book this produces a realized PV profit margin of roughly 8.3%
against a 10% target -- the gap is rate-table granularity, not a deliberate margin difference,
since both premiums target the same `assumptions.target_profit_margin`.

This module invents no new pricing formula: every premium and cash-flow number it produces comes
from the same `life_pricing.mortality` / `life_pricing.projection` / `life_pricing.premium` /
`life_pricing.cashflow` functions every other loop uses, just run once per policy (or once per
rate cell) instead of once for a single representative policy. See `tests/test_portfolio_pricing.py`
for the regression tests covering this, including that `indicated_pv_profit_margin` hits the
target margin exactly and that `book_premium` produces genuine realized-margin dispersion.

## Experience simulation basis (Loop 8 only -- not a pricing assumption)

The pricing engine (Loops 2-7) uses only the assumptions declared above: the 2015 VBT mortality
tables, the base lapse table, 5.16% interest, and the stated expenses. Loop 8 (experience
analytics / A-E) needs something different: a stochastic *actual* outcome per synthetic policy to
compare against those *expected* assumptions. Because this project has no real policyholder
experience data, that actual outcome is simulated using a second, separately declared basis.

**A/E lapse denominator corrected in V1.1.** The projection has always defined competing
decrements as `D_t = I_t * q_t` (death) and `L_t = I_t * (1 - q_t) * l_t` (lapse) -- a lapse can
only be observed among lives that did not die that year. `life_pricing.experience`'s Monte Carlo
simulation already respected this correctly: it only samples a lapse event when the simulated
policy did not die that year. But the *expected* side of the A/E ratio did not mirror it -- the
exposure table aggregated expected lapses using the raw table rate `l_t` alone, as if every
in-force life were equally exposed to lapsing regardless of that year's mortality. Because
`l_t` is systematically larger than the correct at-risk probability `(1 - q_t) * l_t`, this
understated the A/E lapse ratio (a smaller expected denominator makes actual-over-expected look
larger than it should relative to the correctly conditioned basis).

The exposure table now carries both probabilities explicitly: `expected_death_probability =
expected_qx` and `expected_lapse_probability = (1 - expected_qx) * expected_lapse_rate`, and
`life_pricing.experience.actual_to_expected_by_segment` / `overall_actual_to_expected` sum the
latter as the A/E lapse denominator instead of the raw table rate. See
`tests/test_experience.py::test_ae_lapse_denominator_uses_competing_decrement_not_raw_rate` for a
regression test proving the corrected denominator is strictly smaller than the old (buggy) one.

**Updated in Loop 12**: `true_mortality_multiplier` was originally one flat scalar (1.15, i.e.
"actual mortality runs 15% worse than priced"). It is now a duration-keyed curve,
`true_mortality_multiplier_by_duration`, derived from the SOA ILEC 2012-2019 Mortality Experience
Report, Appendix H (20-year term, actual-to-2015-VBT-expected ratios by duration):

| Duration | Multiplier | Duration | Multiplier |
|---|---:|---|---:|
| 1 | 0.8525 | 11 | 0.7525 |
| 2 | 0.8576 | 12 | 0.7525 |
| 3 | 0.9093 | 13 | 0.7525 |
| 4 | 0.8064 | 14 | 0.7525 |
| 5 | 0.8064 | 15 | 0.7525 |
| 6 | 0.7902 | 16 | 0.7354 |
| 7 | 0.7902 | 17 | 0.7354 |
| 8 | 0.7902 | 18 | 0.7354 |
| 9 | 0.7902 | 19 | 0.7354 |
| 10 | 0.7902 | 20 | 0.7354 |

Notably, real ILEC experience for this product runs *better* than the 2015 VBT expected basis at
every duration (all multipliers < 1.0) -- the opposite direction from the earlier illustrative
1.15 guess. This is a plausible and common pattern (insured lives who buy 20-year term and pass
underwriting tend to experience mortality somewhat better than a broad industry-average table
would predict) and is exactly the kind of thing a real A/E study is meant to surface; it was kept
as-is rather than adjusted to match the old assumption, per AGENTS.md's rule against silently
altering assumptions to preserve a prior result.

Appendix H's most recent issue-year cohort (2010-2017) does not yet have observed experience past
duration 10 (recent business hasn't aged that far), so durations 11-20 above are spliced in from
the next-older issue-year cohort (2000-2009) at the same durations -- the only cohort in the
report with full duration 1-20 coverage. See `docs/DATA_SOURCES.md` for the exact source cells.

**Loop 12b update**: `true_lapse_multiplier` was originally an unchanged, illustrative flat
scalar (0.85), because the SOA persistency report used for the *expected* lapse basis was thought
to have no independent "actual" counterpart. On closer inspection, the same 2009-13 persistency
workbook reports a genuinely different real cut of the same underlying study: sheet
"Term - Part 3" ("By Risk Classification"), which breaks the 20-Year level term lapse curve out by
risk class (Preferred / Standard / Substandard) rather than blending them, as sheet "Term -Part 1"
(the pricing/expected source) does. The **Standard** risk class was used -- the only one of the
three with reported experience at every duration 1-20 (Preferred and Substandard have no reported
figures for durations 18-20, presumably too little exposure to report reliably). Dividing this
Standard-class curve by the pricing (expected, blended) curve gives a real, duration-varying
`true_lapse_multiplier_by_duration`:

| Duration | Multiplier | Duration | Multiplier |
|---|---:|---|---:|
| 1 | 1.4667 | 11 | 1.0667 |
| 2 | 1.2909 | 12 | 1.0741 |
| 3 | 1.2553 | 13 | 1.0370 |
| 4 | 1.2326 | 14 | 1.0400 |
| 5 | 1.2250 | 15 | 1.0000 |
| 6 | 1.1081 | 16 | 1.0345 |
| 7 | 1.0294 | 17 | 1.2069 |
| 8 | 1.0000 | 18 | 1.2353 |
| 9 | 1.0000 | 19 | 1.1667 |
| 10 | 1.0667 | 20 | 0.5484 |

Two things are worth flagging honestly. First, this is not a fully *independent* dataset in the
statistical sense -- both curves come from the same 2009-13 experience period, just sliced
differently (blended-across-risk-class vs. Standard-only) -- so it demonstrates real, reported
variation rather than a truly separate "actual" study. Second, duration 20's multiplier (0.5484)
is a genuine reported figure but rests on very thin exposure for the Standard-only cut at that
duration (the sheet's own exposure-distribution column shows only ~0.2% of the risk class's
policies are still being observed at duration 20), so it carries much less credibility than the
early-duration figures; it was still used as-is (not smoothed or discarded) per AGENTS.md's rule
against silently altering reported data, but a future loop could apply an explicit credibility
blend toward 1.0 at low-exposure durations. Both caveats are why this remains flagged as a "true"
*simulation* basis for Loop 8 rather than promoted into the pricing (expected) assumptions
themselves.

| Parameter | Value | Meaning |
|---|---:|---|
| `experience_simulation.true_mortality_multiplier_by_duration` | see table above | Real, SOA-ILEC-derived, duration-varying. |
| `experience_simulation.true_lapse_multiplier_by_duration` | see table above | Real, SOA-persistency-by-risk-class-derived, duration-varying (Loop 12b). |

These values exist so Loop 8's actual-to-expected (A/E) ratios are not trivially 1.0 -- they let
the experience analytics engine demonstrate a realistic, data-grounded divergence between actual
and priced experience. They are:

- Never read by the pricing engine (`life_pricing.premium`, `life_pricing.cashflow`,
  `life_pricing.projection`) -- only by `life_pricing.experience`.
- Clearly namespaced under `experience_simulation` in `config/assumptions.yaml`, separate from
  `mortality` and `lapse`, and every output column they influence is named `actual_*` rather than
  `expected_*`, per AGENTS.md's rule against mixing actual experience with expected assumptions
  without labeling them.

## Assumption governance

Every assumption must:
1. Be declared in `config/assumptions.yaml`.
2. Be validated before projections run.
3. Be overridable in scenario tests without changing source code.
4. Have a documented unit and interpretation.
