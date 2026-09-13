# P2 Productization Roadmap

Date: 2026-09-13

P2 turns the validated P1 system into an installable product with external
workflow integration and market-facing evidence.

## 1. GitHub Webhook / PR gate

Status: implemented

- `POST /api/integrations/github/webhook`
- HMAC SHA-256 signature verification.
- Repository-dispatch and pull-request payload support.
- Release gate generated from the persisted report.
- PR comment posted through the GitHub API.
- No credentials or webhook secrets are persisted.

## 2. Release audit template

Status: implemented

- Self-serve historical-release retrospective.
- Inputs: baseline/candidate versions, run id, CI artifacts.
- Outputs: decision, evidence, root cause, remediation, approver section.

## 3. Public open-source patch regression case

Status: implemented as a controlled public-dependency case

- Run against a real upstream patch in a public repository.
- Preserve the patch and source revision.
- Publish reproducible commands and the resulting decision.

## 4. Competitor capability matrix

Status: implemented

- Compare release-gate behavior against LangSmith, Braintrust, Langfuse,
  DeepEval, Galileo, and Promptfoo.
- Separate factual public claims from assumptions.

## 5. Adoption and pricing experiments

Status: external

- Publish the self-hosted release audit.
- Measure downloads, forks, CI installs, and conversion.
- Run one paid or written pilot without inventing results.

## 6. OOD planning benchmark

Status: implemented

- Measure deterministic and model planning on failure signatures not present in
  the bundled fixtures.
- Report accuracy, rationale coverage, tokens, and failure modes.
