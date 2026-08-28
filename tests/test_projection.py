from pathlib import Path

import pytest

from life_pricing.config import load_assumptions
from life_pricing.projection import ProjectionInputError, project_policy

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "assumptions.yaml"

FACE_AMOUNT = 250_000
ISSUE_AGE = 35


@pytest.fixture
def assumptions():
    return load_assumptions(CONFIG_PATH)


@pytest.fixture
def synthetic_qx(assumptions):
    """Synthetic, monotonically increasing mortality curve for exercising the
    projection math only. This is NOT a real mortality table -- Loop 3 wires
    in the actual 2017-CSO-based curve; this engine just consumes whatever
    q_x series it is given.
    """
    term = assumptions.term_years
    return [0.001 + 0.001 * t for t in range(term)]


def _project(assumptions, synthetic_qx, **overrides):
    kwargs = dict(
        issue_age=ISSUE_AGE,
        mortality_rates_qx=synthetic_qx,
        face_amount=FACE_AMOUNT,
    )
    kwargs.update(overrides)
    return project_policy(assumptions, **kwargs)


def test_beginning_inforce_year_one_equals_one(assumptions, synthetic_qx):
    records = _project(assumptions, synthetic_qx)
    assert records[0].beginning_inforce_probability == pytest.approx(1.0)


def test_probabilities_are_in_unit_interval(assumptions, synthetic_qx):
    records = _project(assumptions, synthetic_qx)
    for r in records:
        for value in (
            r.beginning_inforce_probability,
            r.death_probability,
            r.lapse_probability,
            r.ending_inforce_probability,
        ):
            assert 0.0 <= value <= 1.0


def test_decrements_reconcile_beginning_inforce(assumptions, synthetic_qx):
    records = _project(assumptions, synthetic_qx)
    for r in records:
        total = r.death_probability + r.lapse_probability + r.ending_inforce_probability
        assert total == pytest.approx(r.beginning_inforce_probability)


def test_inforce_is_nonincreasing(assumptions, synthetic_qx):
    records = _project(assumptions, synthetic_qx)
    path = [records[0].beginning_inforce_probability] + [r.ending_inforce_probability for r in records]
    for earlier, later in zip(path, path[1:]):
        assert later <= earlier + 1e-12


def test_discount_factors_positive_and_nonincreasing(assumptions, synthetic_qx):
    records = _project(assumptions, synthetic_qx)
    factors = [r.discount_factor for r in records]
    assert all(f > 0 for f in factors)
    for earlier, later in zip(factors, factors[1:]):
        assert later <= earlier


def test_premium_and_maintenance_discount_factors_positive_and_nonincreasing(assumptions, synthetic_qx):
    records = _project(assumptions, synthetic_qx)
    for attr in ("discount_factor_premium", "discount_factor_maintenance"):
        factors = [getattr(r, attr) for r in records]
        assert all(f > 0 for f in factors)
        for earlier, later in zip(factors, factors[1:]):
            assert later <= earlier


def test_premium_discount_factor_is_one_year_ahead_of_claim_discount_factor(assumptions, synthetic_qx):
    # v_b(t) = (1+i)^-(t-1) = (1+i) * (1+i)^-t = (1+i) * v_e(t) -- beginning-
    # of-year timing is exactly one year of interest "ahead of" end-of-year
    # timing, for every policy year.
    records = _project(assumptions, synthetic_qx)
    rate = assumptions.discount_rate
    for r in records:
        assert r.discount_factor_premium == pytest.approx(r.discount_factor * (1.0 + rate))


def test_maintenance_discount_factor_is_between_premium_and_claim(assumptions, synthetic_qx):
    records = _project(assumptions, synthetic_qx)
    for r in records:
        assert r.discount_factor <= r.discount_factor_maintenance <= r.discount_factor_premium


def test_expected_claim_equals_death_probability_times_face(assumptions, synthetic_qx):
    records = _project(assumptions, synthetic_qx)
    for r in records:
        assert r.expected_death_benefit == pytest.approx(r.death_probability * FACE_AMOUNT)


def test_mismatched_mortality_length_is_rejected(assumptions):
    with pytest.raises(ProjectionInputError):
        project_policy(assumptions, issue_age=ISSUE_AGE, mortality_rates_qx=[0.01, 0.02], face_amount=FACE_AMOUNT)


def test_out_of_range_qx_is_rejected(assumptions, synthetic_qx):
    bad_qx = list(synthetic_qx)
    bad_qx[0] = 1.5
    with pytest.raises(ProjectionInputError):
        _project(assumptions, bad_qx)


def test_issue_age_outside_configured_range_is_rejected(assumptions, synthetic_qx):
    with pytest.raises(ProjectionInputError):
        _project(assumptions, synthetic_qx, issue_age=10)


def test_nonpositive_face_amount_is_rejected(assumptions, synthetic_qx):
    with pytest.raises(ProjectionInputError):
        _project(assumptions, synthetic_qx, face_amount=0)


def test_zero_interest_gives_unit_discount_factors(assumptions, synthetic_qx):
    from copy import deepcopy

    raw = deepcopy(assumptions.raw)
    raw["interest"]["annual_effective_rate"] = 0.0
    from life_pricing.config import ProjectAssumptions

    zero_interest_assumptions = ProjectAssumptions(raw=raw)
    records = _project(zero_interest_assumptions, synthetic_qx)
    for r in records:
        assert r.discount_factor == pytest.approx(1.0)
        assert r.discount_factor_premium == pytest.approx(1.0)
        assert r.discount_factor_maintenance == pytest.approx(1.0)
