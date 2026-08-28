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
  (`config/assumptions.yaml`: `mortality.underwriting_class_multiplier_by_face_band`) were
  originally (Loop 3) arbitrary illustrative multipliers with no data behind them; **as of Loop
  12** they are derived from real, published SOA ILEC 2012-2019 Mortality Experience Report
  A/E-by-risk-class data, claims-weighted and face-amount-band-specific (Loop 12b -- see
  `docs/DATA_SOURCES.md`). They are still not a specific insurer's filed underwriting
  relativities -- no company's actual pricing manual is public -- but they are no longer an
  unfounded guess or a single number that discards real face-amount variation.
- **Lapse rates were originally illustrative; as of Loop 12 they are real.**
  `config/assumptions.yaml`'s `lapse.by_duration` now comes from the SOA "2009-13 US Individual
  Life Persistency Update" report's 20-Year level term experience (see `docs/DATA_SOURCES.md`),
  including the real 31% end-of-level-period shock lapse at duration 20. This is genuine industry
  experience, not a company-specific or forward-looking assumption -- persistency patterns can
  shift over time and by distribution channel, product design, and economic conditions, so this
  remains a historical benchmark rather than a guaranteed future rate.
- **No real policyholder data for the portfolio itself; Loop 8's "actual" basis is real data on a
  different cut of the same study, not an independent experience dataset.** The portfolio (Loop 4)
  is fully synthetic. Loop 8's "actual" experience is a *simulation* against a second, separately
  declared basis (`experience_simulation`): both `true_mortality_multiplier_by_duration` (Loop 12,
  from ILEC) and `true_lapse_multiplier_by_duration` (Loop 12b, from a by-risk-class cut of the
  2009-13 Persistency Update) are now real, duration-varying, cited data rather than arbitrary
  scalars (see `docs/DATA_SOURCES.md`). But genuine, statistically-independent A/E analysis needs
  an actual experience dataset collected separately from whatever was used to set pricing
  assumptions; here, both "true" curves are different segmentations of the *same* underlying
  studies used for the *expected* basis (ILEC for mortality, the same 2009-13 persistency workbook
  for lapse), not a second, independent experience source. The lapse curve's duration-20 figure in
  particular rests on very thin reported exposure (~0.2% of the risk class still observed at that
  duration) and should be read as illustrative of a real, reported pattern rather than a precise
  estimate.

- **Interest rate is a real risk-free rate, not a company's actual net investment income
  assumption.** `config/assumptions.yaml`'s `interest.annual_effective_rate` was originally
  (Loop 1) an arbitrary illustrative 4.0%; **as of Loop 12** it is the real 20-Year Treasury
  Constant Maturity yield (FRED series DGS20, 5.16% as of 2026-08-25 -- see
  `docs/DATA_SOURCES.md`). This is a genuine, citable public rate, but it is a risk-free proxy: a
  real insurer prices using its expected portfolio yield, which typically earns a spread over
  Treasuries from investment-grade corporate bonds and other assets backing reserves, and this
  project does not model that spread, the underlying asset portfolio, or interest-rate risk (a
  full stochastic interest-rate model is explicitly out of scope per `PROJECT_SPEC.md` section 9).
  It is also a point-in-time snapshot of a daily-updated series -- unlike the mortality/lapse
  studies above, which describe a fixed historical experience period, this rate can and will drift
  from the market by the time anyone reads this.

## Structural simplifications

- **Single discrete annual cash flow per policy year, still true within a component.** V1
  through Loop 12 discounted `(Prem_t - Claim_t - Expense_t)` by one shared `v_t = (1+i)^-t` per
  policy year, even though `PROJECT_SPEC.md` section 2 describes premiums as paid at the start of
  the year and claims at the end -- a cross-component inconsistency. **Corrected in V1.1**:
  premiums and acquisition expense now discount at `v_b(t) = (1+i)^-(t-1)` (beginning of year),
  claims still at `v_t = (1+i)^-t` (end of year), and maintenance expense at a deliberately chosen
  mid-year `v_m(t) = (1+i)^-(t-0.5)`. See ACTUARIAL_ASSUMPTIONS.md "Cash-flow timing (V1.1)" for
  the full derivation. What remains a genuine simplification even after this fix: cash flow within
  a policy year is still a single point-in-time event per component (e.g. every maintenance dollar
  lands at exactly mid-year, not spread continuously), not full continuous-time intra-year timing
  -- a further refinement, not something this project claims to already model.
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
