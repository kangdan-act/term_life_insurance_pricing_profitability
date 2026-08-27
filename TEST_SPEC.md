# Test Specification

## Gate A — Configuration

The project must fail fast when:
- issue_age_min > issue_age_max
- term_years <= 0
- discount_rate <= -1
- target_profit_margin is outside [0, 1)
- any lapse rate is outside [0, 1]
- any expense is negative

## Gate B — Projection identities

For a deterministic policy projection:
- beginning in-force in year 1 equals 1
- all probabilities are in [0, 1]
- death + lapse + ending in-force reconciles beginning in-force
- in-force probability is non-increasing
- PV factors are positive and non-increasing for positive interest
- expected claim equals death probability × face amount

## Gate C — Pricing

When Loop 5 is implemented:
- break-even premium produces approximately zero PV profit
- target premium produces target PV profit margin within tolerance
- indicated premium increases when mortality increases
- indicated premium increases when expenses increase
- indicated premium decreases when discount rate increases, all else equal
- no negative premiums

## Gate D — Edge cases

Test:
- age 25 and age 60
- minimum and maximum face amount
- smoker/nonsmoker
- each underwriting class
- zero lapse scenario
- zero expense scenario
- zero interest scenario
- high mortality stress

## Gate E — Reproducibility

- synthetic portfolio generation uses explicit random seed
- tests do not depend on notebook execution order
- no network access is required to run core unit tests after source data are downloaded
