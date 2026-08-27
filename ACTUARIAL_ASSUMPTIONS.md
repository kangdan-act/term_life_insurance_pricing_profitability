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
  table (config/assumptions.yaml: mortality.underwriting_class_multiplier = Preferred Plus 0.60,
  Preferred 0.80, Standard 1.00). These are V1 illustrative relativities, not filed industry
  rates, and are declared as configuration exactly like every other assumption in this document.
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

Base duration lapse assumption:

| Policy year | Annual lapse |
|---|---:|
| 1 | 8.0% |
| 2 | 7.0% |
| 3 | 6.0% |
| 4–5 | 5.0% |
| 6–10 | 4.0% |
| 11–20 | 3.0% |

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
experience data, that actual outcome is simulated using a second, separately declared basis:

| Parameter | Value | Meaning |
|---|---:|---|
| `experience_simulation.true_mortality_multiplier` | 1.15 | Simulated "true" mortality runs 15% higher than the pricing (expected) mortality basis. |
| `experience_simulation.true_lapse_multiplier` | 0.85 | Simulated "true" lapse runs 15% lower than the pricing (expected) lapse basis. |

These values exist purely so Loop 8's actual-to-expected (A/E) ratios are not trivially 1.0 --
they let the experience analytics engine demonstrate a realistic "mortality worse than priced,
lapse better than priced" pattern. They are:

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
