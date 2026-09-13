# P0 Verification Record

Date: 2026-09-13

## Published video

- Bilibili: https://www.bilibili.com/video/BV1mPYY6sE1k
- Direct MP4 backup: https://n.uguu.se/AFnrdUSF.mp4
- Local v2 video: `release/EvalPilot-competition-demo-v2.mp4`
- Bilibili title: `EvalPilot｜AI应用回归评测数字员工｜自主规划与反事实根因定位`
- Model-plan panel: 1:10–1:25

## Clean-worktree acceptance

Clean worktree: `.runtime/p0-clean-20260913-114040`

- Backend full test suite: pass.
- Frontend: 153 tests pass.
- Frontend TypeScript check: pass.
- Frontend production build: pass.
- Basic E2E: 31/31 checks pass.
- V2 autonomous-investigation E2E: pass.
- Public Haystack external-SUT E2E: pass.

## Live same-run verification

- Run: `18c66a9f-93fe-4941-bd9d-cea35f604a76`
- Investigation: `17880a87-246e-4328-b967-77c464c5e4cd`
- LLM steps: 3
- Model-guided replay plans: 1
- Judge calls: 52
- Counterfactuals: 8
- Decision: BLOCK / CRITICAL
- Total tokens: 78,695
- Compute: 474.00 seconds
- Logical storage: 0.2500 MB
- Peak cost: $0.264697
- Off-peak cost: $0.138935

## Public open-source SUT

- Engine: `haystack-ai 3.1.1`
- Source: https://github.com/deepset-ai/haystack
- Same-revision control: 0 regressions, mean delta 0.
- Baseline vs candidate: 8 regressions, mean delta -0.173.
- Counterfactual replays: 8 through HTTP.
- Offline cache replay: exact match.
- SUT unavailable with empty cache: loud failure, no mock fallback.

## Planning comparison

- Deterministic: 8/8 correct, 0 model tokens.
- DeepSeek V4 Pro: 8/8 correct, 6,651 tokens, 100% rationale coverage.
- Conclusion: deterministic planning wins on cost for the closed benchmark; model planning remains a bounded extensibility path.

## Competition status

Internal self-assessment: 90/100.
Submission link and paperwork are ready; the remaining action is form submission by the user.
