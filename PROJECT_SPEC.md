# Project Specification

## 1. Business question

Given applicant and policy characteristics, what annual level premium should an insurer charge
so that expected discounted premiums cover expected death benefits, expenses, and the target profit?

The engine must also identify which customer segments create or destroy expected value and quantify
how sensitive profitability is to mortality, lapse, expense, interest, and premium assumptions.

## 2. V1 product contract

| Item | V1 specification |
|---|---|
| Product | Simplified 20-year level term life |
| Issue ages | 25–60 inclusive |
| Term | 20 policy years |
| Premium mode | Annual, beginning of policy year while in force |
| Death benefit | Level face amount |
| Benefit timing | End of policy year of death |
| Face amount | $100,000–$1,000,000 in synthetic portfolio |
| Sex variable | Female / Male, to match public mortality table dimensions |
| Smoking | Nonsmoker / Smoker |
| Underwriting class | Preferred Plus / Preferred / Standard |
| Currency | USD |
| Projection basis | Annual discrete-time expected-value projection |

## 3. Required policy-level inputs

- policy_id
- issue_age
- sex
- smoker_status
- underwriting_class
- face_amount
- term_years
- annual_premium (observed/current or solved)
- issue_year
- distribution_channel (for segmentation)
- state_region (coarse region only, for segmentation)

## 4. Required projection outputs by policy-year

- policy_year
- attained_age
- beginning_inforce_probability
- mortality_rate_qx
- lapse_rate
- death_probability
- lapse_probability
- ending_inforce_probability
- expected_premium
- expected_death_benefit
- acquisition_expense
- maintenance_expense
- premium_related_expense
- net_cash_flow
- discount_factor
- present_value_net_cash_flow

## 5. Required policy-level summary outputs

- pv_premiums
- pv_claims
- pv_expenses
- pv_profit
- pv_profit_margin
- indicated_annual_premium
- break_even_annual_premium

## 6. Portfolio outputs

Aggregate by:
- issue age band
- sex
- smoking status
- underwriting class
- face amount band
- distribution channel
- issue cohort

Metrics:
- policy count
- face amount
- premium
- expected claims
- expected expenses
- PV profit
- PV profit margin
- A/E mortality
- A/E lapse

## 7. Core actuarial identities

For policy year t:

Beginning in-force probability:
I_1 = 1

Death probability:
D_t = I_t * q_t

Lapse probability (competing decrement approximation):
L_t = I_t * (1 - q_t) * l_t

Ending in-force probability:
I_(t+1) = I_t * (1 - q_t) * (1 - l_t)

Expected annual premium:
Prem_t = I_t * P

Expected death benefit:
Claim_t = D_t * Face

Discount factor:
v_t = (1 + i)^(-t)

PV Profit:
PVProfit = sum_t v_t * (Prem_t - Claim_t - Expense_t)

Target profit margin:
Margin = PVProfit / PVPremium

The indicated premium is the premium P that satisfies:
PVProfit / PVPremium = target_margin

## 8. Engineering requirements

- All assumptions must live outside calculation code.
- Projection functions must be deterministic for fixed inputs.
- Every core actuarial identity must have unit tests.
- No notebook may contain unique business logic.
- Source functions require type hints and docstrings.
- Scenario assumptions must be reproducible from configuration.
- Project must run from a fresh environment using documented commands.

## 9. Out of scope for v1

- Stochastic interest-rate models
- Dynamic policyholder behavior
- Reinsurance
- Taxes
- Statutory reserves / VM-20 implementation
- Capital modeling / RBC
- Monthly projection frequency
- Full underwriting rules engine

These can be added after the core pricing engine is validated.
