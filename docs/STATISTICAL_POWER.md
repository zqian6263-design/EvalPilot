# Statistical Power Diagnostics

Date: 2026-09-13

Every report now includes paired-sample power diagnostics:

```text
minimum_detectable_effect
required_matched_cases
observed_power
sample_size_adequate
```

## Method

For a one-sided 95% regression test with 80% target power:

```text
standard_error = sd(paired_differences) / sqrt(n)
mde = (z_0.95 + z_0.80) * standard_error
required_n = ceil((z_0.95 + z_0.80)^2 * sd^2 / threshold^2)
```

These values are diagnostic, not a new release decision. The measured paired
interval and the per-case evidence remain authoritative.

## Product rule

- If `sample_size_adequate` is false, the report must say that small samples may
  make the aggregate interval inconclusive.
- A localized hard failure remains blocking even when aggregate power is low.
- A clean aggregate result must not be used to dismiss a separately confirmed
  per-case regression.
- The minimum detectable effect is reported so reviewers can see what magnitude
  the current run could have detected.

## Tests

`backend/tests/test_power.py` covers identical pairs, variable pairs, and
undersized samples. The integration test verifies that every run report exposes
the four diagnostic fields.
