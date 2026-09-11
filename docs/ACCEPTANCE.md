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

## Submission materials

- Product name, team description, and detailed description are finalized.
- Two- to three-minute demo video is publicly accessible without login.
- PPT or PDF matches the live product.
- GitHub or code archive contains setup instructions.
- All claims in the pitch are demonstrated in the product or clearly labeled as roadmap.
