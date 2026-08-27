"""Mortality data layer (Loop 3).

Parses the raw SOA mort.soa.org-format table exports under data/raw/ into
select-and-ultimate q_x lookups, and exposes a single function that turns
(issue_age, sex, smoker_status, underwriting_class) into the q_x curve the
projection engine (life_pricing.projection) needs.

Data provenance note: the four files under data/raw/ are the SOA 2015 VBT
Smoker Distinct select-and-ultimate tables, not 2017 CSO as originally
drafted in Loop 1's ACTUARIAL_ASSUMPTIONS.md. See docs/DATA_SOURCES.md for
the correction. Per that document's provenance rule, raw files are never
edited by hand; this module reads them as-is and writes any derived form to
data/processed/.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pandas as pd

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
RAW_DATA_DIR = PACKAGE_ROOT / "data" / "raw"
PROCESSED_DATA_DIR = PACKAGE_ROOT / "data" / "processed"

# sex, smoker_status (both lowercased) -> source filename under data/raw/
_SOURCE_FILES: dict[tuple[str, str], str] = {
    ("female", "nonsmoker"): "Non_Smoker_Female.xls",
    ("male", "nonsmoker"): "Non_Smoker_Male.xls",
    ("female", "smoker"): "Smoke_Female.xls",
    ("male", "smoker"): "Smoker_Male.xls",
}

_TABLE_MARKER = "Table # "
_HEADER_MARKER = "Row\\Column"


class MortalityDataError(ValueError):
    """Raised when mortality source data cannot be parsed or a lookup is out of range."""


@dataclass(frozen=True)
class SelectUltimateTable:
    """A parsed select-and-ultimate mortality table for one sex/smoker cell.

    select.loc[issue_age, duration] -> q_x for a policy issued at issue_age,
    in its `duration`-th policy year (1-indexed, matches PROJECT_SPEC.md's
    D_t = I_t * q_t notation).
    ultimate.loc[attained_age] -> q_x once a duration falls outside the
    table's select period (unused for the V1 20-year term product, whose
    term is shorter than the select period, but implemented for
    completeness and for future products).
    """

    select: pd.DataFrame
    ultimate: pd.Series
    source_file: str


def _find_table_marker_rows(raw: pd.DataFrame) -> list[int]:
    return raw.index[raw[0] == _TABLE_MARKER].tolist()


def _read_block(raw: pd.DataFrame, start_row: int, end_row: int, source_file: str) -> pd.DataFrame:
    """Read one 'Row\\Column' data block (age rows x id columns) from the raw sheet."""

    header_row = None
    for i in range(start_row, end_row):
        if raw.iloc[i, 0] == _HEADER_MARKER:
            header_row = i
            break
    if header_row is None:
        raise MortalityDataError(
            f"{source_file}: could not find a '{_HEADER_MARKER}' header row "
            f"within rows [{start_row}, {end_row})."
        )

    header = raw.iloc[header_row]
    value_columns = [c for c in raw.columns if c != 0 and pd.notna(header[c])]
    column_ids = [int(header[c]) for c in value_columns]

    data = raw.iloc[header_row + 1 : end_row, [0] + value_columns].copy()
    data.columns = ["age"] + column_ids
    data = data.dropna(subset=["age"])

    if data.empty:
        raise MortalityDataError(f"{source_file}: data block starting row {header_row} is empty.")

    data["age"] = data["age"].astype(int)
    data = data.set_index("age").astype(float)
    return data


def parse_soa_table_file(path: Path) -> SelectUltimateTable:
    """Parse one SOA mort.soa.org-format .xls export into select & ultimate tables.

    The expected file layout (confirmed against all four files in
    data/raw/) is: a metadata preamble, a 'Table # 1' select block (rows =
    issue age, columns = policy duration), and a 'Table # 2' ultimate block
    (rows = attained age, single q_x column).
    """

    if not path.exists():
        raise MortalityDataError(f"Mortality source file not found: {path}")

    raw = pd.read_excel(path, sheet_name=0, header=None)
    markers = _find_table_marker_rows(raw)
    if len(markers) != 2:
        raise MortalityDataError(
            f"{path.name}: expected exactly 2 '{_TABLE_MARKER}' blocks (select, ultimate), "
            f"found {len(markers)}."
        )

    select_start, ultimate_start = markers
    select = _read_block(raw, select_start, ultimate_start, path.name)
    ultimate_df = _read_block(raw, ultimate_start, len(raw), path.name)

    if ultimate_df.shape[1] != 1:
        raise MortalityDataError(
            f"{path.name}: expected the ultimate block to have exactly one q_x column, "
            f"found {ultimate_df.shape[1]}."
        )
    ultimate = ultimate_df.iloc[:, 0]
    ultimate.name = "q_x"

    return SelectUltimateTable(select=select, ultimate=ultimate, source_file=path.name)


@lru_cache(maxsize=None)
def load_mortality_table(sex: str, smoker_status: str) -> SelectUltimateTable:
    """Load (and cache) the parsed select-and-ultimate table for one sex/smoker cell."""

    key = (sex.lower(), smoker_status.lower())
    if key not in _SOURCE_FILES:
        raise MortalityDataError(
            f"No mortality table configured for sex={sex!r}, smoker_status={smoker_status!r}. "
            f"Expected sex in {{'male','female'}} and smoker_status in {{'smoker','nonsmoker'}}."
        )
    return parse_soa_table_file(RAW_DATA_DIR / _SOURCE_FILES[key])


def select_qx_series(
    table: SelectUltimateTable,
    issue_age: int,
    term_years: int,
    multiplier: float = 1.0,
) -> list[float]:
    """Return one q_x per policy year (1..term_years) for a policy issued at issue_age.

    Uses select-period rates (indexed by issue age and duration) while the
    duration is within the table's select period, and falls back to the
    ultimate table (indexed by attained age) for any later durations.
    `multiplier` is applied multiplicatively and the result clamped to
    [0, 1] -- this is how underwriting-class and mortality-stress
    adjustments are layered onto the base table (see
    ACTUARIAL_ASSUMPTIONS.md).
    """

    if issue_age not in table.select.index:
        raise MortalityDataError(
            f"issue_age {issue_age} is outside {table.source_file}'s select table age range "
            f"[{table.select.index.min()}, {table.select.index.max()}]."
        )
    if term_years <= 0:
        raise MortalityDataError("term_years must be positive.")

    select_period = table.select.shape[1]
    qx: list[float] = []
    for duration in range(1, term_years + 1):
        if duration <= select_period:
            base_q = float(table.select.loc[issue_age, duration])
        else:
            attained_age = issue_age + duration - 1
            if attained_age not in table.ultimate.index:
                raise MortalityDataError(
                    f"attained_age {attained_age} is outside {table.source_file}'s ultimate "
                    f"table age range [{table.ultimate.index.min()}, {table.ultimate.index.max()}]."
                )
            base_q = float(table.ultimate.loc[attained_age])

        adjusted_q = min(max(base_q * multiplier, 0.0), 1.0)
        qx.append(adjusted_q)

    return qx


def mortality_curve_for_policy(
    assumptions,
    issue_age: int,
    sex: str,
    smoker_status: str,
    underwriting_class: str,
) -> list[float]:
    """Full Loop 3 entry point: assumptions + policy characteristics -> q_x curve.

    Combines the base sex/smoker select-and-ultimate table with the
    configured underwriting-class multiplier and mortality stress
    multiplier (config/assumptions.yaml -> mortality section), both applied
    multiplicatively as ACTUARIAL_ASSUMPTIONS.md specifies.
    """

    table = load_mortality_table(sex, smoker_status)
    multiplier = (
        assumptions.underwriting_class_multiplier(underwriting_class)
        * assumptions.mortality_stress_multiplier
    )
    return select_qx_series(table, issue_age, assumptions.term_years, multiplier=multiplier)


def write_processed_tables(output_dir: Path = PROCESSED_DATA_DIR) -> list[Path]:
    """Parse every raw source table once and write tidy CSVs to data/processed/.

    Implements docs/DATA_SOURCES.md's provenance rule: raw files are never
    edited, and every derived form is both reproducible from source code and
    persisted under data/processed/ rather than data/raw/.
    """

    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    for (sex, smoker_status), filename in _SOURCE_FILES.items():
        table = parse_soa_table_file(RAW_DATA_DIR / filename)

        select_out = output_dir / f"mortality_select_{sex}_{smoker_status}.csv"
        table.select.to_csv(select_out)
        written.append(select_out)

        ultimate_out = output_dir / f"mortality_ultimate_{sex}_{smoker_status}.csv"
        table.ultimate.to_csv(ultimate_out)
        written.append(ultimate_out)

    return written


if __name__ == "__main__":
    paths = write_processed_tables()
    for p in paths:
        print(f"wrote {p}")
