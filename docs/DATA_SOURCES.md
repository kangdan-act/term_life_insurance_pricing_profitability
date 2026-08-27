# Data Sources

## Mortality reference

Actual source, as parsed by `life_pricing.mortality` (Loop 3) from `data/raw/`:
- Society of Actuaries Mortality and Other Rate Tables (mort.soa.org)
- 2015 Valuation Basic Table (VBT) Smoker Distinct tables, Age Nearest Birthday
  (Table Identity 3265 family), select and ultimate.
- Four files, one per sex x smoker-status cell: `Non_Smoker_Female.xls`, `Non_Smoker_Male.xls`,
  `Smoke_Female.xls` (female smoker), `Smoker_Male.xls`.
- Each file contains two blocks: a select table (issue age 18-95 x duration 1-25) and an
  ultimate table (attained age 18-120). Source citation embedded in each file: "American Academy
  of Actuaries along with the Society of Actuaries ... 2015 Valuation Basic Tables ... developed
  based on the mortality experience from the SOA Individual Life Experience Committee studies
  from the 2002-2009 study period ... projected from March 1st, 2006 to July 1st, 2015."

### Correction: this project originally targeted 2017 CSO

`ACTUARIAL_ASSUMPTIONS.md` and `config/assumptions.yaml` originally (Loop 1) named "2017 CSO
unloaded" as the mortality basis, written before any raw file had actually been parsed. When
Loop 3 opened the four files under `data/raw/`, their embedded metadata identified them as 2015
VBT Smoker Distinct tables, not 2017 CSO. Rather than relabeling this data as "2017 CSO" (which
would misrepresent the source) or silently keeping the inaccurate label in the docs, both
`ACTUARIAL_ASSUMPTIONS.md` and `config/assumptions.yaml` were corrected to describe the 2015 VBT
basis that the engine actually uses. If a true 2017 CSO unloaded table is later placed in
`data/raw/`, `life_pricing.mortality`'s parser would need a small format-specific update (the
SOA export layout differs table to table) and the reference_basis config value updated again.

## Select period methodology (per the official 2015 VBT Report)

Per the SOA's own "2015 Valuation Basic Table Report" (Dec 2018,
https://www.soa.org/globalassets/assets/Files/resources/experience-studies/2018/2015-vbt-report.pdf),
the select period is not a flat 25 years for everyone -- it varies by issue age and sex, reflecting
how long underwriting selection effects take to "wear off":

| Issue age | Male select period | Female select period |
|---|---:|---:|
| 0-17 | 0 (ultimate only) | 0 (ultimate only) |
| 18-54 | 25 years | 20 years |
| ~70 | 17 years | 15 years |
| 90-95 | 1-4 years | 1-4 years |

Selection was determined separately by sex but applied uniformly across smoker status.

This project's raw select tables (data/raw/*.xls) still have 25 duration columns for every age and
both sexes -- SOA published a uniform 25-column grid, with cells beyond an age/sex's true select
period presumably already converged toward ultimate-equivalent values (the file format does not
mark this distinction). Because this project's V1 product term is only 20 years
(config/assumptions.yaml: product.term_years), `life_pricing.mortality.select_qx_series` reads
select-table durations 1-20 for every issue age, which stays within or at the true select period
boundary for every age/sex in the configured issue-age range (25-60) except very old issue ages
near the 55+ band, where the true select period can run shorter than 20 years (e.g. ~17 select
years at issue age 70) -- outside this project's issue_age_max=60, so not currently reachable, but
worth flagging if issue_age_max is ever raised in a future loop.

## Underwriting class is not in the raw mortality-table data

PROJECT_SPEC.md requires `underwriting_class` (Preferred Plus / Preferred / Standard) as a
policy-level input, but the 2015 VBT select/ultimate table files split only by sex and smoker
status -- they do not encode underwriting class. Loop 3 layered a configured multiplicative
relativity (`config/assumptions.yaml`: `mortality.underwriting_class_multiplier`) on top of the
base sex/smoker table to produce a class-adjusted q_x curve; those Loop 3 values were arbitrary
illustrative guesses (0.60 / 0.80 / 1.00), not derived from any data.

**Loop 12 update**: these relativities were replaced with values derived from a real, published
industry study -- the SOA "Individual Life Experience Committee (ILEC) 2012-2019 Mortality
Experience Report" appendices (`ilec-mort-appendices.xlsx`, user-supplied, downloadable from
mort.soa.org / soa.org's experience-studies pages), sheet **`K1`** ("Appendix K1 - Nonsmoker
experience for preferred plans by risk class structure and face amount bands"), expected basis
2015 VBT (the same table family used for the base mortality curve above, so the relativity is
consistent with this project's mortality basis).

Sheet `K1` reports actual-to-expected (A/E) mortality ratios by risk-class rank (1 = best/lowest
mortality ... N = worst/highest mortality), separately for each declared risk-class structure
(2-class, 3-class, 4-class) and face-amount band, across duration groups (1, 2, 3, 4-5, 6-10,
11-15, 16-20, 21-25). This project uses a 3-class structure (Preferred Plus / Preferred /
Standard), so only the **3-class rows** were used, for the three face-amount bands nearest this
project's `face_amount_min`/`face_amount_max` range ($100K-$1M):

| Face amount band | Class rank 1 (best) row | Class rank 2 row | Class rank 3 (worst) row |
|---|---:|---:|---:|
| 100,000-249,999 | K1!12 | K1!13 | K1!14 |
| 250,000-499,999 | K1!21 | K1!22 | K1!23 |
| 500,000-999,999 | K1!30 | K1!31 | K1!32 |

Methodology: for each face-amount band, the reported A/E ratios across all eight duration groups
(columns E:L on sheet `K1`) were averaged within each class rank to get one A/E figure per
(band, rank); that figure was then normalized within the band by dividing by the rank-3
(Standard/worst) figure, so Standard = 1.0 and better classes get multipliers < 1.0. The
normalized ratios were then averaged across the three face-amount bands to get one relativity per
class, giving the values now in `config/assumptions.yaml`
(`mortality.underwriting_class_multiplier`): Preferred Plus 0.6357, Preferred 0.7425,
Standard 1.0000.

These are still not filed, company-specific underwriting relativities -- no single insurer's
actual pricing manual is public -- but they are now grounded in real, published aggregate
industry A/E experience by risk class, rather than an arbitrary guess. A reader can reproduce or
refine this calculation directly from the cited `K1` sheet rows (e.g. weighting by the "Number of
Policy Claims" block reported later on the same sheet, rows 63-65 / 72-74 / 81-83, instead of a
simple average, would be a reasonable refinement for a future loop).

## Experience-study benchmark (Loop 8's "true" mortality basis)

The Society of Actuaries has published individual life mortality experience materials, including
large delimited datasets and pivot-table specifications. The V1 portfolio itself remains fully
synthetic (Loop 4) so the project stays reproducible on a normal development machine, but Loop 8's
experience-analytics engine needs a stochastic "actual" outcome to compare against the pricing
(expected) basis (see `ACTUARIAL_ASSUMPTIONS.md`'s "Experience simulation basis" section).

**Loop 12 update**: `experience_simulation.true_mortality_multiplier` was originally one flat,
arbitrary scalar (1.15). It was replaced with a duration-varying curve,
`true_mortality_multiplier_by_duration`, sourced from the same ILEC 2012-2019 Mortality Experience
Report workbook as above (`ilec-mort-appendices.xlsx`), sheet **`H`** ("Appendix H - Experience
for term 10, 15 and 20 plans by level term period and issue year ranges"), the "A/E Ratio by
Amount" table (expected basis: 2015 VBT - Primary Table), filtered to `Level Term Period (yrs) =
20` (this project's product):

| Sheet `H` row | Issue Year Range | Duration columns populated |
|---|---|---|
| 16 | 2010-2017 | 1, 2, 3, 4-5, 6-10 (durations 1-10) |
| 15 | 2000-2009 | 3, 4-5, 6-10, 11-15, 16-20 (durations 3-20) |

The most recent issue-year cohort (2010-2017, row 16) has not yet aged past duration 10, so it has
no reported experience for durations 11-20 (those cells are blank/zero in the source). Durations
11-20 were therefore spliced in from the next-older cohort (2000-2009, row 15) at the same
durations -- the oldest cohort in the report with data reaching duration 16-20. This produces the
`true_mortality_multiplier_by_duration` values now in `config/assumptions.yaml`: row 16's values
for durations 1-10 (0.8525, 0.8576, 0.9093, 0.8064, 0.8064, 0.7902 x5 for durations 6-10, since
the source reports a single "6-10" duration-group figure applied to each of those five durations),
then row 15's values for durations 11-20 (0.7525 x5 for 11-15, 0.7354 x5 for 16-20). See
`ACTUARIAL_ASSUMPTIONS.md` for the full table and the interpretation (real experience for this
product runs better than the 2015 VBT expected basis at every duration).

`experience_simulation.true_lapse_multiplier` (0.85) was left unchanged and remains illustrative
-- the persistency report used as the *expected* lapse basis (see "Lapse experience" section
below) cannot also serve as an independent "actual" comparison for the same product.

## Lapse experience (real 20-Year level term persistency data)

**Loop 12 update**: `lapse.by_duration` in `config/assumptions.yaml` was originally an
illustrative declining curve invented for V1 (8% at duration 1, declining to a flat 3% by
duration 11+), not derived from any data source.

It was replaced with the real, published SOA "2009-13 US Individual Life Persistency Update"
report (`2009-13-us-ind-life-persistency-excel.xlsx`, user-supplied, downloadable from soa.org's
experience-studies pages), covering experience period 2009-2013. Sheet **`Term -Part 1`**, the
"Term Insurance ... Policy Lapse Rates" block for the **"20-Year level term"** plan (columns
V:X / 22:24 -- "Policy Year", "Lapse Rate", "Exposure Distribution" -- rows 10 through 29 for
policy years 1 through 20), gives the exact per-duration lapse rates now in
`config/assumptions.yaml`. The source reports lapse rates as percentages (e.g. `6` meaning 6.0%);
these were converted to decimal fractions (`0.06`) to match this project's convention.

Duration 20's reported lapse rate is 31.0% -- far above the level-period rates (3-6%) -- which is
the real, well-documented "shock lapse" that occurs when a level-term policy's premium jumps to
attained-age rates at the end of the level-premium period. See `ACTUARIAL_ASSUMPTIONS.md` for the
full duration table and interpretation.

## Data provenance rule

Raw external source files must be stored under `data/raw/` and never manually edited.
Any transformation must be reproducible in source code and write to `data/processed/`.

The two SOA reference workbooks used for the Loop 12 rigor upgrade (`ilec-mort-appendices.xlsx`
and `2009-13-us-ind-life-persistency-excel.xlsx`) were used as one-time, manual reference sources
to derive the config values documented above; they are not read programmatically by any code in
this repository (unlike `data/raw/*.xls`, which `life_pricing.mortality` parses directly at
runtime), so they are not committed to this repository, consistent with `.gitignore`'s existing
`data/raw/*` / `data/processed/*` exclusions for third-party source data. Both are freely
downloadable from the Society of Actuaries' public experience-studies pages for independent
verification of every figure cited above.
