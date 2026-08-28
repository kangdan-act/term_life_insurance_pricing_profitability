from pathlib import Path

import pytest

from life_pricing.config import load_assumptions
from life_pricing.mortality import (
    MortalityDataError,
    load_mortality_table,
    mortality_curve_for_policy,
    select_qx_series,
)

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "assumptions.yaml"


@pytest.fixture
def assumptions():
    return load_assumptions(CONFIG_PATH)


@pytest.fixture(params=[
    ("male", "nonsmoker"),
    ("female", "nonsmoker"),
    ("male", "smoker"),
    ("female", "smoker"),
])
def sex_smoker(request):
    return request.param


def test_all_four_source_tables_parse(sex_smoker):
    sex, smoker_status = sex_smoker
    table = load_mortality_table(sex, smoker_status)
    assert table.select.shape[0] == 78  # ages 18-95
    assert table.select.shape[1] == 25  # durations 1-25
    assert table.ultimate.shape[0] == 103  # ages 18-120


def test_known_select_cells_non_smoker_male():
    table = load_mortality_table("male", "nonsmoker")
    assert table.select.loc[35, 1] == pytest.approx(0.00015)
    assert table.select.loc[18, 1] == pytest.approx(0.00069)


def test_unknown_sex_smoker_combo_raises():
    with pytest.raises(MortalityDataError):
        load_mortality_table("male", "unrated")


def test_select_qx_series_length_and_range(sex_smoker):
    table = load_mortality_table(*sex_smoker)
    qx = select_qx_series(table, issue_age=40, term_years=20)
    assert len(qx) == 20
    for q in qx:
        assert 0.0 <= q <= 1.0


def test_select_qx_series_uses_select_table_when_within_select_period():
    table = load_mortality_table("male", "nonsmoker")
    qx = select_qx_series(table, issue_age=35, term_years=20)
    expected = [float(table.select.loc[35, d]) for d in range(1, 21)]
    assert qx == pytest.approx(expected)


def test_select_qx_series_falls_back_to_ultimate_beyond_select_period():
    table = load_mortality_table("male", "nonsmoker")
    # select period is 25 durations; ask for 30 to force ultimate fallback
    qx = select_qx_series(table, issue_age=30, term_years=30)
    assert len(qx) == 30
    for d in range(1, 26):
        assert qx[d - 1] == pytest.approx(float(table.select.loc[30, d]))
    for d in range(26, 31):
        attained_age = 30 + d - 1
        assert qx[d - 1] == pytest.approx(float(table.ultimate.loc[attained_age]))


def test_issue_age_outside_select_table_raises():
    table = load_mortality_table("male", "nonsmoker")
    with pytest.raises(MortalityDataError):
        select_qx_series(table, issue_age=10, term_years=20)


def test_multiplier_scales_and_clamps():
    table = load_mortality_table("male", "nonsmoker")
    base = select_qx_series(table, issue_age=35, term_years=20, multiplier=1.0)
    halved = select_qx_series(table, issue_age=35, term_years=20, multiplier=0.5)
    for b, h in zip(base, halved):
        assert h == pytest.approx(b * 0.5)

    huge = select_qx_series(table, issue_age=35, term_years=20, multiplier=1_000_000)
    assert all(q == pytest.approx(1.0) for q in huge)


@pytest.mark.parametrize("issue_age", [25, 60])
@pytest.mark.parametrize("underwriting_class", ["Preferred Plus", "Preferred", "Standard"])
def test_mortality_curve_for_policy_edge_ages_and_classes(assumptions, issue_age, underwriting_class):
    qx = mortality_curve_for_policy(
        assumptions,
        issue_age=issue_age,
        sex="male",
        smoker_status="nonsmoker",
        underwriting_class=underwriting_class,
        face_amount=300_000,
    )
    assert len(qx) == assumptions.term_years
    assert all(0.0 <= q <= 1.0 for q in qx)


def test_preferred_plus_is_strictly_lighter_than_standard(assumptions):
    pp = mortality_curve_for_policy(
        assumptions, issue_age=40, sex="male", smoker_status="nonsmoker",
        underwriting_class="Preferred Plus", face_amount=300_000,
    )
    std = mortality_curve_for_policy(
        assumptions, issue_age=40, sex="male", smoker_status="nonsmoker",
        underwriting_class="Standard", face_amount=300_000,
    )
    assert all(p <= s for p, s in zip(pp, std))
    assert any(p < s for p, s in zip(pp, std))


def test_unknown_underwriting_class_raises(assumptions):
    with pytest.raises(Exception):
        mortality_curve_for_policy(
            assumptions, issue_age=40, sex="male", smoker_status="nonsmoker",
            underwriting_class="Super Preferred", face_amount=300_000,
        )


def test_underwriting_class_multiplier_varies_by_face_amount_band(assumptions):
    # Loop 12b: the underwriting-class relativity is now face-amount-band
    # specific (derived from ILEC Appendix K1), so the same class at two
    # different face amounts should generally not produce identical curves.
    low_band = mortality_curve_for_policy(
        assumptions, issue_age=40, sex="male", smoker_status="nonsmoker",
        underwriting_class="Preferred Plus", face_amount=150_000,
    )
    high_band = mortality_curve_for_policy(
        assumptions, issue_age=40, sex="male", smoker_status="nonsmoker",
        underwriting_class="Preferred Plus", face_amount=750_000,
    )
    assert low_band != high_band


def test_face_amount_outside_every_band_raises(assumptions):
    with pytest.raises(Exception):
        mortality_curve_for_policy(
            assumptions, issue_age=40, sex="male", smoker_status="nonsmoker",
            underwriting_class="Standard", face_amount=-1,
        )
