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

## Underwriting class is not in the raw data

PROJECT_SPEC.md requires `underwriting_class` (Preferred Plus / Preferred / Standard) as a
policy-level input, but the 2015 VBT files split only by sex and smoker status. Loop 3 layers a
configured multiplicative relativity (`config/assumptions.yaml`:
`mortality.underwriting_class_multiplier`) on top of the base sex/smoker table to produce a
class-adjusted q_x curve. These relativities are V1 illustrative assumptions, not derived from
the source data or any filed table -- see `ACTUARIAL_ASSUMPTIONS.md` for the values and rationale.

## Experience-study benchmark

The Society of Actuaries has published individual life mortality experience materials, including
large delimited datasets and pivot-table specifications. These may be used in a later loop for
experience benchmarking, but the V1 portfolio itself remains synthetic so the project is fully
reproducible and manageable on a normal development machine.

## Data provenance rule

Raw external source files must be stored under `data/raw/` and never manually edited.
Any transformation must be reproducible in source code and write to `data/processed/`.
