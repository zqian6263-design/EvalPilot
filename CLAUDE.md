# EvalPilot Collaboration Contract

## Mission

Build a working MVP by 2026-09-19 for the AI+Super Agent university track. The product must be demonstrable end to end and must produce evidence-backed evaluation artifacts.

## Non-negotiables

1. Keep the first demo focused on a knowledge-base QA or customer-support application.
2. Every evaluation finding must link to evidence: exact input, output, tool trace, and evaluator rationale.
3. Never store API keys in Git. Use `.env.example` only.
4. Default execution must not run arbitrary untrusted code. The Python tool is allowlisted and disabled unless explicitly enabled.
5. Prefer small, testable modules over a large framework.
6. Any agent editing this repo must update only its assigned worktree and report changed paths and verification commands.

## Repository conventions

- Backend: Python 3.11+, FastAPI, Pydantic v2, SQLite for MVP.
- Frontend: React + TypeScript + Vite.
- Tests: pytest for backend, Vitest/Playwright where practical.
- API contract: `docs/INTERFACES.md` is the source of truth.
- Product contract: `docs/SPEC.md` is the source of truth.
- Use UTC ISO-8601 timestamps.
- IDs: UUID strings.
- Do not rename shared contract fields without updating docs first.

## Definition of done for the MVP

- One command starts the backend and frontend.
- A seeded demo run can be opened from the UI.
- The run shows planner tasks, tool execution, evidence, scores, and a regression report.
- At least one deliberately regressed version is detected with a clear explanation.
- README contains exact setup and demo instructions.
