# AGENTS.md — AI Development Contract

This repository is an actuarial modeling project. Correctness has priority over code volume.

## Required workflow for every change

1. Read `PROJECT_SPEC.md`, `ACTUARIAL_ASSUMPTIONS.md`, and `TEST_SPEC.md`.
2. State which actuarial identity or engineering requirement the change implements.
3. Make the smallest coherent code change.
4. Add or update tests.
5. Run the relevant tests.
6. Explain any actuarial assumption introduced or changed.
7. Do not silently alter assumptions to make tests pass.

## Prohibited behavior

- Do not hard-code pricing assumptions inside calculation functions.
- Do not invent mortality rates when a configured table should supply them.
- Do not replace actuarial formulas with ML predictions without an explicit challenger-model step.
- Do not delete failing tests merely to obtain a green test suite.
- Do not put core logic only in notebooks.
- Do not mix actual experience measures with expected assumptions without labeling them.

## Definition of done

A change is complete only when:
- code runs,
- tests pass,
- actuarial reconciliation passes,
- assumptions are documented,
- outputs are reproducible.

## Review checklist

Ask:
- Are decrement probabilities ordered and applied consistently?
- Is benefit timing consistent with discount timing?
- Are premiums paid only while in force?
- Are expenses applied at the intended timing?
- Are mortality/lapse rates probabilities rather than hazards?
- Are present values calculated using the declared annual effective rate?
- Does any scenario unintentionally mutate the base configuration?
