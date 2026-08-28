"""Configuration loader and validation for actuarial assumptions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class AssumptionValidationError(ValueError):
    """Raised when actuarial assumptions are internally inconsistent."""


@dataclass(frozen=True)
class ProjectAssumptions:
    """Validated project assumptions used by the pricing engine."""

    raw: dict[str, Any]

    # -- product -----------------------------------------------------

    @property
    def issue_age_min(self) -> int:
        return int(self.raw["product"]["issue_age_min"])

    @property
    def issue_age_max(self) -> int:
        return int(self.raw["product"]["issue_age_max"])

    @property
    def term_years(self) -> int:
        return int(self.raw["product"]["term_years"])

    @property
    def face_amount_min(self) -> float:
        return float(self.raw["product"]["face_amount_min"])

    @property
    def face_amount_max(self) -> float:
        return float(self.raw["product"]["face_amount_max"])

    # -- interest / profit --------------------------------------------

    @property
    def discount_rate(self) -> float:
        return float(self.raw["interest"]["annual_effective_rate"])

    @property
    def target_profit_margin(self) -> float:
        return float(self.raw["profit"]["target_pv_margin"])

    # -- lapse ----------------------------------------------------------

    @property
    def lapse_rates(self) -> dict[int, float]:
        return {int(k): float(v) for k, v in self.raw["lapse"]["by_duration"].items()}

    # -- mortality --------------------------------------------------------

    @property
    def mortality_reference_basis(self) -> str:
        return str(self.raw["mortality"]["reference_basis"])

    @property
    def mortality_stress_multiplier(self) -> float:
        return float(self.raw["mortality"]["stress_multiplier"])

    @property
    def underwriting_class_multiplier_bands(self) -> list[dict[str, Any]]:
        """Each band: {"face_amount_min": float, "face_amount_max": float,
        "multipliers": {underwriting_class: float}}. See
        config/assumptions.yaml: mortality.underwriting_class_multiplier_by_face_band."""

        bands = []
        for band in self.raw["mortality"]["underwriting_class_multiplier_by_face_band"]:
            bands.append(
                {
                    "face_amount_min": float(band["face_amount_min"]),
                    "face_amount_max": float(band["face_amount_max"]),
                    "multipliers": {
                        str(k): float(v) for k, v in band["multipliers"].items()
                    },
                }
            )
        return bands

    @property
    def underwriting_classes(self) -> set[str]:
        """The set of underwriting-class category names (identical across
        every face-amount band; enforced by validate_assumptions)."""

        bands = self.underwriting_class_multiplier_bands
        return set(bands[0]["multipliers"]) if bands else set()

    def underwriting_class_multiplier(self, underwriting_class: str, face_amount: float) -> float:
        """Look up the underwriting-class relativity for the face-amount
        band `face_amount` falls in (bands are inclusive on both ends and
        collectively cover [product.face_amount_min, product.face_amount_max];
        see validate_assumptions)."""

        for band in self.underwriting_class_multiplier_bands:
            if band["face_amount_min"] <= face_amount <= band["face_amount_max"]:
                multipliers = band["multipliers"]
                if underwriting_class not in multipliers:
                    raise AssumptionValidationError(
                        f"Unknown underwriting_class {underwriting_class!r}; "
                        f"expected one of {sorted(multipliers)}."
                    )
                return multipliers[underwriting_class]
        raise AssumptionValidationError(
            f"face_amount {face_amount} is not covered by any "
            "mortality.underwriting_class_multiplier_by_face_band entry."
        )

    # -- expenses -----------------------------------------------------

    @property
    def acquisition_fixed_expense(self) -> float:
        return float(self.raw["expenses"]["acquisition_fixed"])

    @property
    def acquisition_pct_first_year_premium(self) -> float:
        return float(self.raw["expenses"]["acquisition_pct_first_year_premium"])

    @property
    def renewal_pct_premium(self) -> float:
        return float(self.raw["expenses"]["renewal_pct_premium"])

    @property
    def maintenance_per_inforce_year(self) -> float:
        return float(self.raw["expenses"]["maintenance_per_inforce_year"])

    # -- synthetic data ----------------------------------------------------

    @property
    def random_seed(self) -> int:
        return int(self.raw["synthetic_data"]["random_seed"])

    @property
    def n_policies(self) -> int:
        return int(self.raw["synthetic_data"]["n_policies"])

    @property
    def sex_distribution(self) -> dict[str, float]:
        return {str(k): float(v) for k, v in self.raw["synthetic_data"]["sex_distribution"].items()}

    @property
    def smoker_distribution(self) -> dict[str, float]:
        return {
            str(k): float(v) for k, v in self.raw["synthetic_data"]["smoker_distribution"].items()
        }

    @property
    def underwriting_class_distribution(self) -> dict[str, float]:
        return {
            str(k): float(v)
            for k, v in self.raw["synthetic_data"]["underwriting_class_distribution"].items()
        }

    @property
    def distribution_channel_distribution(self) -> dict[str, float]:
        return {
            str(k): float(v)
            for k, v in self.raw["synthetic_data"]["distribution_channel"].items()
        }

    @property
    def state_region_distribution(self) -> dict[str, float]:
        return {
            str(k): float(v) for k, v in self.raw["synthetic_data"]["state_region"].items()
        }

    @property
    def issue_year_min(self) -> int:
        return int(self.raw["synthetic_data"]["issue_year_min"])

    @property
    def issue_year_max(self) -> int:
        return int(self.raw["synthetic_data"]["issue_year_max"])

    @property
    def face_amount_round_to(self) -> float:
        return float(self.raw["synthetic_data"]["face_amount_round_to"])

    # -- experience simulation (Loop 8 "true" basis, NOT a pricing assumption) --

    @property
    def true_mortality_multiplier_by_duration(self) -> dict[int, float]:
        return {
            int(k): float(v)
            for k, v in self.raw["experience_simulation"]["true_mortality_multiplier_by_duration"].items()
        }

    @property
    def true_lapse_multiplier_by_duration(self) -> dict[int, float]:
        return {
            int(k): float(v)
            for k, v in self.raw["experience_simulation"]["true_lapse_multiplier_by_duration"].items()
        }


def _require_nonnegative(value: float, field_name: str) -> None:
    if value < 0:
        raise AssumptionValidationError(f"{field_name} must be nonnegative.")


def _require_positive(value: float, field_name: str) -> None:
    if value <= 0:
        raise AssumptionValidationError(f"{field_name} must be positive.")


def _require_probability_distribution(dist: dict[str, Any], field_name: str) -> None:
    if not dist:
        raise AssumptionValidationError(f"{field_name} must declare at least one category.")
    total = 0.0
    for category, weight in dist.items():
        weight = float(weight)
        if weight < 0:
            raise AssumptionValidationError(f"{field_name}[{category}] must be nonnegative.")
        total += weight
    if abs(total - 1.0) > 1e-6:
        raise AssumptionValidationError(f"{field_name} weights must sum to 1.0, got {total}.")


def validate_assumptions(raw: dict[str, Any]) -> None:
    """Validate core actuarial and product assumptions."""

    product = raw["product"]
    interest = raw["interest"]
    profit = raw["profit"]
    lapse = raw["lapse"]["by_duration"]
    expenses = raw["expenses"]
    mortality = raw["mortality"]
    synthetic = raw["synthetic_data"]

    if int(product["issue_age_min"]) > int(product["issue_age_max"]):
        raise AssumptionValidationError("issue_age_min cannot exceed issue_age_max.")

    if int(product["term_years"]) <= 0:
        raise AssumptionValidationError("term_years must be positive.")

    if float(product["face_amount_min"]) > float(product["face_amount_max"]):
        raise AssumptionValidationError("face_amount_min cannot exceed face_amount_max.")

    discount_rate = float(interest["annual_effective_rate"])
    if discount_rate <= -1.0:
        raise AssumptionValidationError("annual_effective_rate must be greater than -1.")

    target_margin = float(profit["target_pv_margin"])
    if not 0.0 <= target_margin < 1.0:
        raise AssumptionValidationError("target_pv_margin must be in [0, 1).")

    expected_durations = set(range(1, int(product["term_years"]) + 1))
    actual_durations = {int(k) for k in lapse}
    if actual_durations != expected_durations:
        missing = sorted(expected_durations - actual_durations)
        extra = sorted(actual_durations - expected_durations)
        raise AssumptionValidationError(
            f"lapse table must cover every policy year exactly; missing={missing}, extra={extra}"
        )

    for duration, rate in lapse.items():
        rate = float(rate)
        if not 0.0 <= rate <= 1.0:
            raise AssumptionValidationError(
                f"lapse rate for duration {duration} must be in [0, 1]."
            )

    for name, value in expenses.items():
        _require_nonnegative(float(value), f"expenses.{name}")

    _require_positive(float(mortality["stress_multiplier"]), "mortality.stress_multiplier")

    bands = mortality.get("underwriting_class_multiplier_by_face_band", [])
    if not bands:
        raise AssumptionValidationError(
            "mortality.underwriting_class_multiplier_by_face_band must declare at least one band."
        )

    parsed_bands = []
    for i, band in enumerate(bands):
        band_min = float(band["face_amount_min"])
        band_max = float(band["face_amount_max"])
        if band_min > band_max:
            raise AssumptionValidationError(
                f"underwriting_class_multiplier_by_face_band[{i}]: face_amount_min "
                f"cannot exceed face_amount_max."
            )
        multipliers = band.get("multipliers", {})
        if not multipliers:
            raise AssumptionValidationError(
                f"underwriting_class_multiplier_by_face_band[{i}] must declare at least one class."
            )
        for class_name, multiplier in multipliers.items():
            _require_positive(
                float(multiplier),
                f"underwriting_class_multiplier_by_face_band[{i}].multipliers[{class_name}]",
            )
        parsed_bands.append({"min": band_min, "max": band_max, "classes": set(multipliers)})

    first_uw_categories = parsed_bands[0]["classes"]
    for i, band in enumerate(parsed_bands):
        if band["classes"] != first_uw_categories:
            raise AssumptionValidationError(
                "every underwriting_class_multiplier_by_face_band entry must declare the same "
                f"underwriting classes; band[0]={sorted(first_uw_categories)} vs "
                f"band[{i}]={sorted(band['classes'])}."
            )

    sorted_bands = sorted(parsed_bands, key=lambda b: b["min"])
    product_face_min = float(product["face_amount_min"])
    product_face_max = float(product["face_amount_max"])
    if sorted_bands[0]["min"] > product_face_min:
        raise AssumptionValidationError(
            "underwriting_class_multiplier_by_face_band does not cover "
            f"product.face_amount_min ({product_face_min})."
        )
    if sorted_bands[-1]["max"] < product_face_max:
        raise AssumptionValidationError(
            "underwriting_class_multiplier_by_face_band does not cover "
            f"product.face_amount_max ({product_face_max})."
        )
    for prev_band, next_band in zip(sorted_bands, sorted_bands[1:]):
        if next_band["min"] != prev_band["max"] + 1:
            raise AssumptionValidationError(
                "underwriting_class_multiplier_by_face_band entries must be contiguous with no "
                f"gap or overlap; band ending {prev_band['max']} is followed by band starting "
                f"{next_band['min']} (expected {prev_band['max'] + 1})."
            )

    underwriting_categories = first_uw_categories

    _require_positive(int(synthetic["n_policies"]), "synthetic_data.n_policies")
    _require_positive(float(synthetic["face_amount_round_to"]), "synthetic_data.face_amount_round_to")

    if int(synthetic["issue_year_min"]) > int(synthetic["issue_year_max"]):
        raise AssumptionValidationError("synthetic_data.issue_year_min cannot exceed issue_year_max.")

    # The underwriting_class_distribution categories must exactly match the
    # face-band multiplier tables' categories -- otherwise the portfolio
    # generator could produce policies with no mortality relativity defined.
    uw_dist_categories = set(synthetic.get("underwriting_class_distribution", {}))
    if uw_dist_categories != underwriting_categories:
        raise AssumptionValidationError(
            "synthetic_data.underwriting_class_distribution categories must match "
            "mortality.underwriting_class_multiplier_by_face_band categories; "
            f"got {sorted(uw_dist_categories)} vs {sorted(underwriting_categories)}."
        )

    for field_name in (
        "sex_distribution",
        "smoker_distribution",
        "underwriting_class_distribution",
        "distribution_channel",
        "state_region",
    ):
        _require_probability_distribution(synthetic[field_name], f"synthetic_data.{field_name}")

    experience_simulation = raw["experience_simulation"]
    true_mortality_by_duration = experience_simulation["true_mortality_multiplier_by_duration"]
    expected_sim_durations = set(range(1, int(product["term_years"]) + 1))
    actual_sim_durations = {int(k) for k in true_mortality_by_duration}
    if actual_sim_durations != expected_sim_durations:
        missing = sorted(expected_sim_durations - actual_sim_durations)
        extra = sorted(actual_sim_durations - expected_sim_durations)
        raise AssumptionValidationError(
            "experience_simulation.true_mortality_multiplier_by_duration must cover "
            f"every policy year exactly; missing={missing}, extra={extra}"
        )
    for duration, multiplier in true_mortality_by_duration.items():
        _require_positive(
            float(multiplier),
            f"experience_simulation.true_mortality_multiplier_by_duration[{duration}]",
        )
    true_lapse_by_duration = experience_simulation["true_lapse_multiplier_by_duration"]
    actual_lapse_sim_durations = {int(k) for k in true_lapse_by_duration}
    if actual_lapse_sim_durations != expected_sim_durations:
        missing = sorted(expected_sim_durations - actual_lapse_sim_durations)
        extra = sorted(actual_lapse_sim_durations - expected_sim_durations)
        raise AssumptionValidationError(
            "experience_simulation.true_lapse_multiplier_by_duration must cover "
            f"every policy year exactly; missing={missing}, extra={extra}"
        )
    for duration, multiplier in true_lapse_by_duration.items():
        _require_positive(
            float(multiplier),
            f"experience_simulation.true_lapse_multiplier_by_duration[{duration}]",
        )


def load_assumptions(path: str | Path) -> ProjectAssumptions:
    """Load YAML assumptions, validate them, and return an immutable wrapper."""

    path = Path(path)
    with path.open("r", encoding="utf-8") as file:
        raw = yaml.safe_load(file)

    validate_assumptions(raw)
    return ProjectAssumptions(raw=raw)
