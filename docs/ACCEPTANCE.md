# Integration Acceptance Checklist

## Clean start

- Backend install and start commands work from a fresh PowerShell.
- Frontend install and start commands work from a fresh PowerShell.
- No secret is required for the deterministic demo.
- Vite proxy reaches the backend API.

## End-to-end demo

- `/api/demo/seed` or the UI creates a seeded project and run.
- The run transitions through queued, planning, executing, evaluating, and completed.
- At least 10 cases exist across normal, boundary, adversarial, and regression categories.
- Both baseline and candidate results are visible.
- Evidence can be opened for a finding.
- The report identifies a stable regression with confidence and recommendations.
- The result is deterministic enough for repeated demos.

## Quality gates

- Backend tests pass.
- Frontend build passes.
- No API keys, personal data, or absolute local paths are committed.
- The UI works in the intended desktop demo viewport.
- A failure path is shown clearly and does not freeze the UI.
- README documents exact setup commands and a 3-minute demo flow.

## External SUT and bounded agent control

- `scripts/sut-e2e-check.ps1` passes against a separate HTTP process.
- The same-revision control reports zero regressed scenarios.
- The baseline/candidate run reports eight regressed scenarios with a confirmed interval.
- Counterfactual replay traverses the HTTP boundary.
- Offline replay reproduces the same result with the SUT stopped.
- A cache miss with the SUT unavailable fails loudly and never falls back to the mock.
- A live LLM replay plan can change the executed intervention only after allowlist validation; measured results remain authoritative.

## Submission materials

- Product name, team description, and detailed description are finalized.
- Two- to three-minute demo video is publicly accessible without login.
- PPT or PDF matches the live product.
- GitHub or code archive contains setup instructions.
- All claims in the pitch are demonstrated in the product or clearly labeled as roadmap.
