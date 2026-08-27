"""Statistical challenger model (Loop 10).

Fits an interpretable logistic-regression challenger for policy-year
mortality (or lapse) using the Loop 8 simulated experience data, and
compares it against the actuarial baseline -- the pricing engine's own
expected_qx / expected_lapse_rate -- on log-loss and AUC over a held-out
test split.

This is the explicit challenger-model step AGENTS.md requires before any
statistical model may be discussed alongside the actuarial formulas: it
never replaces life_pricing.mortality or life_pricing.premium, which
continue to run on the actuarial baseline only. This module only reports
how a simple statistical model compares.

Design: the challenger's only numeric input is logit(expected_qx) -- the
actuarial baseline's own prediction, on the log-odds scale -- plus a few
one-hot policy-characteristic dummies (sex, smoker_status,
underwriting_class by default). This means the challenger can only ever
*adjust* the actuarial baseline (e.g. "smokers run higher than the table
says"), not invent an unrelated model; a well-specified actuarial baseline
should make this challenger hard to beat.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss, roc_auc_score
from sklearn.model_selection import train_test_split

DEFAULT_CATEGORICAL_FEATURES = ["sex", "smoker_status", "underwriting_class"]
_PROBABILITY_CLIP = (1e-6, 1 - 1e-6)


class ChallengerModelError(ValueError):
    """Raised when challenger model inputs are invalid or a fit cannot be run."""


@dataclass(frozen=True)
class ChallengerResult:
    """Comparison of the statistical challenger against the actuarial baseline."""

    outcome: str  # "death" or "lapse"
    feature_names: list[str]
    coefficients: dict[str, float]
    intercept: float
    baseline_log_loss: float
    challenger_log_loss: float
    baseline_auc: float
    challenger_auc: float
    n_observations: int
    n_events: int

    @property
    def challenger_beats_baseline_log_loss(self) -> bool:
        """Lower log-loss is better; True means the challenger fits the
        held-out data better than just using the actuarial baseline as-is."""
        return self.challenger_log_loss < self.baseline_log_loss


def fit_challenger(
    exposures: pd.DataFrame,
    portfolio: pd.DataFrame,
    outcome: str = "death",
    categorical_features: list[str] | None = None,
    test_size: float = 0.3,
    random_state: int = 20260827,
) -> ChallengerResult:
    """Fit the logistic-regression challenger for one outcome and evaluate
    it against the actuarial baseline on a held-out test split."""

    if outcome not in ("death", "lapse"):
        raise ChallengerModelError(f"outcome must be 'death' or 'lapse', got {outcome!r}.")
    if exposures.empty:
        raise ChallengerModelError("exposures must contain at least one row.")

    categorical_features = (
        categorical_features if categorical_features is not None else DEFAULT_CATEGORICAL_FEATURES
    )
    baseline_col = "expected_qx" if outcome == "death" else "expected_lapse_rate"
    target_col = "actual_death" if outcome == "death" else "actual_lapse"

    merged = exposures.merge(
        portfolio[["policy_id"] + categorical_features], on="policy_id", how="left"
    )

    baseline_p = merged[baseline_col].clip(*_PROBABILITY_CLIP)
    logit_baseline = np.log(baseline_p / (1 - baseline_p))

    dummies = pd.get_dummies(merged[categorical_features], drop_first=False)
    X = pd.concat([logit_baseline.rename("logit_expected"), dummies], axis=1)
    y = merged[target_col].astype(int)

    if y.nunique() < 2:
        raise ChallengerModelError(
            f"outcome {outcome!r} has no variation in this data (all values are {y.iloc[0]}); "
            "cannot fit or evaluate a classifier. Use a larger portfolio/exposure sample."
        )

    X_train, X_test, y_train, y_test, baseline_train, baseline_test = train_test_split(
        X, y, baseline_p, test_size=test_size, random_state=random_state, stratify=y
    )

    model = LogisticRegression(max_iter=1000)
    model.fit(X_train, y_train)

    challenger_pred = np.clip(model.predict_proba(X_test)[:, 1], *_PROBABILITY_CLIP)
    baseline_pred = baseline_test.clip(*_PROBABILITY_CLIP)

    baseline_log_loss = log_loss(y_test, baseline_pred)
    challenger_log_loss = log_loss(y_test, challenger_pred)

    if y_test.nunique() < 2:
        baseline_auc = float("nan")
        challenger_auc = float("nan")
    else:
        baseline_auc = roc_auc_score(y_test, baseline_pred)
        challenger_auc = roc_auc_score(y_test, challenger_pred)

    coefficients = {name: float(coef) for name, coef in zip(X.columns, model.coef_[0])}

    return ChallengerResult(
        outcome=outcome,
        feature_names=list(X.columns),
        coefficients=coefficients,
        intercept=float(model.intercept_[0]),
        baseline_log_loss=float(baseline_log_loss),
        challenger_log_loss=float(challenger_log_loss),
        baseline_auc=float(baseline_auc),
        challenger_auc=float(challenger_auc),
        n_observations=len(y_test),
        n_events=int(y_test.sum()),
    )
