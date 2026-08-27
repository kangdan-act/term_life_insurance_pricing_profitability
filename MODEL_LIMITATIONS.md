# Model Limitations

This document is the Loop 12 audit deliverable required by the roadmap in `README.md`
("Audit, refactor & GitHub release ... model limitations"). It is a plain-language list of where
this V1 engine simplifies reality, so anyone reading the code or results (including a future
version of this project) knows what NOT to treat as a real pricing indication.

## Data substitutions

- **Mortality basis is 2015 VBT, not 2017 CSO.** Loop 1's draft assumptions targeted 2017 CSO
  unloaded tables; the raw files actually available under `data/raw/` turned out to be the SOA
  2015 VBT Smoker Distinct select-and-ultimate tables. `ACTUARIAL_ASSUMPTIONS.md` and
  `docs/DATA_SOURCES.md` were corrected to describe the real data source rather than keep an
  inaccurate label. The two bases are related (both SOA-published, insured-lives, select and
  ultimate) but are not numerically interchangeable.
- **Underwriting class is not in the raw mortality-table data.** The raw 2015 VBT tables split
  mortality by sex and smoker status only. Preferred Plus / Preferred / Standard relativities
  (`config/assumptions.yaml`: `mortality.underwriting_class_multiplier` = 0.6357 / 0.7425 / 1.0000)
  were originally (Loop 3) arbitrary illustrative multipliers with no data behind them; **as of
  Loop 12** they are derived from real, published SOA ILEC 2012-2019 Mortality Experience Report
  A/E-by-risk-class data (see `docs/DATA_SOURCES.md`). They are still not a specific insurer's
  filed underwriting relativities -- no company's actual pricing manual is public -- and the
  averaging-across-face-bands methodology used to collapse the source data to three numbers is a
  simplification, but they are no longer an unfounded guess.
- **Lapse rates were originally illustrative; as of Loop 12 they are real.**
  `config/assumptions.yaml`'s `lapse.by_duration` now comes from the SOA "2009-13 US Individual
  Life Persistency Update" report's 20-Year level term experience (see `docs/DATA_SOURCES.md`),
  including the real 31% end-of-level-period shock lapse at duration 20. This is genuine industry
  experience, not a company-specific or forward-looking assumption -- persistency patterns can
  shift over time and by distribution channel, product design, and economic conditions, so this
  remains a historical benchmark rather than a guaranteed future rate.
- **No real policyholder data for the portfolio itself, and Loop 8's mortality "actual" basis is
  now real data but its lapse "actual" basis is still simulated.** The portfolio (Loop 4) is fully
  synthetic. Loop 8's "actual" experience is a *simulation* against a second, separately declared
  basis (`experience_simulation`): as of Loop 12, `true_mortality_multiplier_by_duration` is a
  real, ILEC-derived duration curve (see `docs/DATA_SOURCES.md`), but `true_lapse_multiplier`
  (0.85) remains an arbitrary illustrative scalar, since the real persistency data above was
  already consumed as the *expected* lapse basis and cannot double as an independent "actual"
  comparison. Real A/E work needs an actual experience dataset independent from whatever was used
  to set pricing assumptions; this project approximates that only on the mortality side.

## Structural simplifications

- **Single discrete annual cash flow per policy year.** `PROJECT_SPEC.md` section 7 discounts
  `(Prem_t - Claim_t - Expense_t)` by one `v_t = (1+i)^-t` per policy year, even though premiums
  are described as paid at the start of the year and claims at the end. This is the V1 contract as
  written and is what every Gate B/C test in this repo verifies against; it is a common
  introductory simplification, not full intra-year cash flow timing.
- **Level annual premium only**, solved in closed form under the assumption that every expense
  component is linear in the premium level. If a future loop adds a non-linear expense/commission
  structure (e.g. a first-year commission cap), `life_pricing.premium.solve_annual_premium` would
  need to change from a closed-form solve to a numerical one.
- **Deterministic, expected-value projection**, not a stochastic/Monte Carlo reserve or capital
  model. `life_pricing.experience`'s simulation exists only to generate a synthetic "actual"
  dataset for Loop 8/10 and is not a stochastic pricing model.
- **Competing-decrement ordering is fixed**: mortality decrement is always applied before lapse
  within a policy year (`D_t = I_t*q_t`, `L_t = I_t*(1-q_t)*l_t`), per `PROJECT_SPEC.md`.

## Explicitly out of scope (per `PROJECT_SPEC.md` section 9)

Stochastic interest-rate models, dynamic policyholder behavior, reinsurance, taxes, statutory
reserves / VM-20, capital modeling / RBC, monthly projection frequency, and a full underwriting
rules engine are all out of scope for V1 and are not implemented anywhere in this codebase.

## Statistical challenger model (Loop 10)

`life_pricing.challenger` fits a single interpretable logistic regression per outcome
(mortality / lapse), trained and evaluated only on the simulated experience data described above.
It exists to demonstrate the actuarial-baseline-vs-statistical-model comparison workflow
(AGENTS.md's required "explicit challenger-model step"), not as a production mortality/lapse
model. Its coefficients reflect the synthetic simulation's built-in bias, not real-world mortality
or lapse patterns.

## What this project is for

This is a learning/portfolio project demonstrating a reproducible actuarial pricing engine
end-to-end: assumptions -> mortality -> projection -> pricing -> profitability -> experience
analytics -> scenario testing -> a statistical challenger -> visualization. It is not a licensed
or filed pricing model and should not be used to set real premiums.
