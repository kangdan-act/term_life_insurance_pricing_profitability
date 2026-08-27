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
  table (config/assumptions.yaml: mortality.underwriting_class_multiplier = Preferred Plus 0.6357,
  Preferred 0.7425, Standard 1.0000). **Updated in Loop 12** from V1 illustrative guesses to values
  derived from real published data: the SOA "Individual Life Experience Committee (ILEC) 2012-2019
  Mortality Experience Report" appendices, Appendix K1 (nonsmoker actual-to-2015-VBT-expected
  ratios by underwriting-class rank and face-amount band), averaged across the 100k-249k /
  250k-499k / 500k-999k face bands and normalized so the worst (Standard) class = 1.0. These are
  still not filed company-specific rates -- they are relativities implied by aggregate industry
  experience data -- but they replace arbitrary guesses with a cited, reproducible source. See
  `docs/DATA_SOURCES.md` for the exact source cells and averaging methodology.
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

Base annual effective discount rate: **4.0%**

Sensitivity range planned:
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

## Experience simulation basis (Loop 8 only -- not a pricing assumption)

The pricing engine (Loops 2-7) uses only the assumptions declared above: the 2015 VBT mortality
tables, the base lapse table, 4.0% interest, and the stated expenses. Loop 8 (experience
analytics / A-E) needs something different: a stochastic *actual* outcome per synthetic policy to
compare against those *expected* assumptions. Because this project has no real policyholder
experience data, that actual outcome is simulated using a second, separately declared basis.

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

`true_lapse_multiplier` remains an unchanged, illustrative flat scalar (0.85): no second,
independent real "actual" lapse dataset was available (the SOA persistency report above was
already consumed as the *expected* lapse basis itself, so it cannot also serve as an independent
"actual" comparison).

| Parameter | Value | Meaning |
|---|---:|---|
| `experience_simulation.true_mortality_multiplier_by_duration` | see table above | Real, SOA-ILEC-derived, duration-varying. |
| `experience_simulation.true_lapse_multiplier` | 0.85 | Still illustrative: simulated "true" lapse runs 15% lower than the pricing (expected) lapse basis. |

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
