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
relativity (`config/assumptions.yaml`: `mortality.underwriting_class_multiplier_by_face_band`) on top of the
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
11-15, 16-20, 21-25) and, in a block further down the same sheet ("Number of Policy Claims",
starting row 58), the claim counts underlying each ratio. This project uses a 3-class structure
(Preferred Plus / Preferred / Standard), so only the **3-class rows** were used, for the three
face-amount bands nearest this project's `face_amount_min`/`face_amount_max` range ($100K-$1M):

| Face amount band | A/E rows (rank 1 / 2 / 3) | Claim-count rows (rank 1 / 2 / 3) |
|---|---|---|
| 100,000-249,999 | K1!12 / K1!13 / K1!14 | K1!63 / K1!64 / K1!65 |
| 250,000-499,999 | K1!21 / K1!22 / K1!23 | K1!72 / K1!73 / K1!74 |
| 500,000-999,999 | K1!30 / K1!31 / K1!32 | K1!81 / K1!82 / K1!83 |

**Loop 12b refinement**: two changes from the original Loop 12 methodology.

1. **Claims-weighted instead of simple average.** For each (band, rank), the eight duration-group
   A/E ratios (columns E:L) are now averaged weighted by that duration group's reported claim
   count (columns E:L of the matching claim-count row), instead of an unweighted mean. This is a
   limited-fluctuation-credibility-style refinement: duration groups with more claims (more
   statistical volume) pull the relativity more than sparse ones -- e.g. the 21-25 duration group
   often has very few claims and an erratic ratio, so it should not count as much as the
   well-populated 6-10 group.
2. **Face-band-specific output instead of one number per class.** The claims-weighted A/E for
   each rank is normalized within its own band (divide by that band's rank-3/Standard figure, so
   Standard = 1.0), rather than normalizing then averaging across bands into one flat number. This
   preserves the real face-amount variation Appendix K1 shows instead of discarding it.

Resulting values in `config/assumptions.yaml`
(`mortality.underwriting_class_multiplier_by_face_band`):

| Face amount band | Preferred Plus | Preferred | Standard |
|---|---:|---:|---:|
| 100,000-249,999 | 0.6541 | 0.7588 | 1.0000 |
| 250,000-499,999 | 0.6433 | 0.7602 | 1.0000 |
| 500,000-1,000,000 | 0.6146 | 0.7182 | 1.0000 |

(The third band's upper bound is set to this project's `product.face_amount_max` of $1,000,000,
one dollar above Appendix K1's own "500,000-999,999" label, so every face amount in the product's
configured range `[100000, 1000000]` falls in exactly one band -- validated in
`life_pricing.config.validate_assumptions`.)

These are still not filed, company-specific underwriting relativities -- no single insurer's
actual pricing manual is public -- but they are now grounded in real, published, claims-weighted,
face-amount-aware industry A/E experience by risk class, rather than an arbitrary guess or a
single flattened average. A reader can reproduce this calculation directly from the cited `K1`
sheet rows and their matching claim-count rows.

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

`experience_simulation.true_lapse_multiplier_by_duration` (Loop 12b) is likewise now real data --
see "Lapse experience" below for its source and derivation.

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

### True lapse basis for Loop 8's experience simulation (Loop 12b)

`experience_simulation.true_lapse_multiplier_by_duration` was derived from a different cut of the
same persistency workbook: sheet **`Term - Part 3`** ("Part 3 of 3 -- By Risk Classification"),
which reports the same "20-year Level Term" lapse rates broken out by risk classification
(Preferred / Standard / Substandard) rather than blended, unlike `Term -Part 1`'s combined figure
used as the pricing/expected basis above. The relevant columns for "20-year Level Term":
Preferred = columns AL:AN (38:40), Standard = columns AP:AR (42:44), Substandard = columns AT:AV
(46:48); rows 10-29 for policy years 1-20.

The **Standard** column was used, because it is the only one of the three with a reported lapse
rate at every duration 1-20 -- Preferred and Substandard both have blank cells for durations
18-20 (the sheet's Exposure Distribution column shows exposure had shrunk too far by then for a
reliable figure to be reported for those classes). `true_lapse_multiplier_by_duration[t]` is
computed as `Standard_lapse_rate[t] / expected_lapse_rate[t]` (the `lapse.by_duration` figure for
the same duration, from the "Lapse experience" section above):

| Duration | Standard (Part 3) | Expected (Part 1) | Multiplier | Duration | Standard (Part 3) | Expected (Part 1) | Multiplier |
|---|---:|---:|---:|---|---:|---:|---:|
| 1 | 8.8% | 6.0% | 1.4667 | 11 | 3.2% | 3.0% | 1.0667 |
| 2 | 7.1% | 5.5% | 1.2909 | 12 | 2.9% | 2.7% | 1.0741 |
| 3 | 5.9% | 4.7% | 1.2553 | 13 | 2.8% | 2.7% | 1.0370 |
| 4 | 5.3% | 4.3% | 1.2326 | 14 | 2.6% | 2.5% | 1.0400 |
| 5 | 4.9% | 4.0% | 1.2250 | 15 | 2.7% | 2.7% | 1.0000 |
| 6 | 4.1% | 3.7% | 1.1081 | 16 | 3.0% | 2.9% | 1.0345 |
| 7 | 3.5% | 3.4% | 1.0294 | 17 | 3.5% | 2.9% | 1.2069 |
| 8 | 3.2% | 3.2% | 1.0000 | 18 | 4.2% | 3.4% | 1.2353 |
| 9 | 3.1% | 3.1% | 1.0000 | 19 | 4.9% | 4.2% | 1.1667 |
| 10 | 3.2% | 3.0% | 1.0667 | 20 | 17.0% | 31.0% | 0.5484 |

Two caveats, stated plainly per AGENTS.md's transparency requirement:

1. This is **not a fully independent dataset** -- both the "expected" and "true" lapse curves come
   from the same 2009-13 experience period and the same underlying policies, just sliced
   differently (blended-across-risk-class vs. Standard-only). It demonstrates real, reported
   variation within the study rather than a genuinely separate "actual" experience study.
2. Duration 20's multiplier (0.5484) rests on very thin exposure -- `Term - Part 3`'s Standard-only
   Exposure Distribution column shows only ~0.2% of that risk class's policies are still being
   observed at duration 20 (vs. ~7-9% at early durations). It is used as reported, unsmoothed, but
   carries materially less credibility than the early-duration figures.

## Interest rate reference (Loop 12)

`interest.annual_effective_rate` in `config/assumptions.yaml` was originally an arbitrary,
illustrative 4.0%, chosen as a round number with no citation. It was replaced with a real,
publicly published rate: the **20-Year Treasury Constant Maturity yield**, FRED series
[`DGS20`](https://fred.stlouisfed.org/series/DGS20) (Federal Reserve Bank of St. Louis, sourced
from the U.S. Treasury), which read **5.16%** as of **2026-08-25** at the time this was checked.

Rationale for this specific series: it is a risk-free rate with roughly the same ~20-year duration
as this product's term, giving a defensible, citable anchor without introducing a full stochastic
interest-rate model (explicitly out of scope per `PROJECT_SPEC.md` section 9 -- see
`MODEL_LIMITATIONS.md`). It is a proxy, not a company's actual net investment income assumption:
a real insurer prices using its expected portfolio yield, typically a spread over Treasuries from
investment-grade corporate bonds and other assets backing reserves, which this project does not
model. Unlike the mortality/lapse sources above, this is a live daily-updated series rather than a
static historical study, so the cited value is a point-in-time snapshot -- re-checking FRED DGS20
and updating this figure (with a new date noted) would be a reasonable periodic refresh for a
project intended to stay current, rather than a one-time correction.

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
