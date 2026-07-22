# Regression tests

Each healed incident is saved here as a small case: the chaos flag that caused it, the expected
SLI breach, and the expected recovery after the remediation. Written by the brain's verifier
(`brain/verify.py → save_regression_test`) so a fixed failure can't silently come back.
