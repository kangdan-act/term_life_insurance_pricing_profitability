from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from life_pricing.config import (
    AssumptionValidationError,
    load_assumptions,
    validate_assumptions,
)

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "assumptions.yaml"


@pytest.fixture
def raw_assumptions():
    with CONFIG_PATH.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def test_base_assumptions_load():
    assumptions = load_assumptions(CONFIG_PATH)
    assert assumptions.issue_age_min == 25
    assert assumptions.issue_age_max == 60
    assert assumptions.term_years == 20
    assert assumptions.discount_rate == pytest.approx(0.04)
    assert assumptions.target_profit_margin == pytest.approx(0.10)
    assert len(assumptions.lapse_rates) == 20


def test_issue_age_range_is_validated(raw_assumptions):
    bad = deepcopy(raw_assumptions)
    bad["product"]["issue_age_min"] = 61
    bad["product"]["issue_age_max"] = 60
    with pytest.raises(AssumptionValidationError):
        validate_assumptions(bad)


@pytest.mark.parametrize("bad_rate", [-0.01, 1.01])
def test_lapse_probability_bounds(raw_assumptions, bad_rate):
    bad = deepcopy(raw_assumptions)
    bad["lapse"]["by_duration"][1] = bad_rate
    with pytest.raises(AssumptionValidationError):
        validate_assumptions(bad)


def test_lapse_table_must_cover_full_term(raw_assumptions):
    bad = deepcopy(raw_assumptions)
    del bad["lapse"]["by_duration"][20]
    with pytest.raises(AssumptionValidationError):
        validate_assumptions(bad)


def test_negative_expense_is_rejected(raw_assumptions):
    bad = deepcopy(raw_assumptions)
    bad["expenses"]["maintenance_per_inforce_year"] = -1
    with pytest.raises(AssumptionValidationError):
        validate_assumptions(bad)
