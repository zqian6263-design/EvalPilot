# P2+ Advanced Productization

Date: 2026-09-13

P2+ closes the gap between “model proposes an intervention” and “the engine can
actually execute it”, while adding real upstream dependency evidence and a
human-label calibration path.

## 1. Executable OOD counterfactuals

Status: implemented and measured

- Added four production intervention names:
  - `retrieval_top_k_restored`
  - `unicode_normalization_restored`
  - `memory_scope_restored`
  - `cache_bypass_enabled`
- The public Haystack SUT implements controlled candidate defects for each.
- Measured baseline -> candidate -> intervention replay: 4/4 root causes.
- Evidence: `docs/OOD_REPLAY_RESULT.json`.

## 2. Real upstream version comparison

Status: implemented

- Independent environments: Haystack 3.0.0 and 3.1.1.
- Same adapter source and same public pipeline.
- 26 scenarios x 2 revision arms = 52 HTTP comparisons.
- 0 semantic mismatches in answers, citations, or refusal behavior.
- Evidence: `docs/UPSTREAM_VERSION_RESULT.json`.

## 3. Human-label judge calibration

Status: harness implemented; labels external

- CSV protocol: `case_id,question,answer,rubric,human_score`.
- Metrics: MAE, signed bias, Pearson correlation, exact agreement.
- Tool: `backend/scripts/judge_calibration.py`.
- No human scores are fabricated or inferred.
- Documentation: `docs/JUDGE_CALIBRATION.md`.

## 4. GitHub App / OAuth

Status: external configuration

The webhook integration is production-ready. A full GitHub App installation
flow requires app registration and private-key storage, which must be done by
the repository owner.

## 5. Public adoption / paid pilot

Status: external

The release audit, GitHub integration, CI artifacts, and public video are ready.
Adoption metrics and paid pilots require a real external user or organization.
