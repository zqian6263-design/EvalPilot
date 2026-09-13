# Public Pages Verification

Date: 2026-09-13

## Published site

- Production URL: https://zqian6263-design.github.io/EvalPilot/
- Published revision: `9087142`
- Repository Homepage: updated and verified through the GitHub API
- Pages source: GitHub Actions (`build_type=workflow`)
- Pages deployment: https://github.com/zqian6263-design/EvalPilot/actions/runs/34748558854
- Main CI: https://github.com/zqian6263-design/EvalPilot/actions/runs/34748558850
- Pull request: https://github.com/zqian6263-design/EvalPilot/pull/13

## Site verification

- Structural and claim checker: pass.
- HTML validation for `index.html` and `404.html`: pass.
- Local HTTP response: `200`, body length `10621`.
- Public HTTP response: `200`, body length `10590`.
- Public assets: `styles.css`, `favicon.svg`, `robots.txt`, `sitemap.xml`, and `404.html` all return `200`.
- Required evidence and video text present in the public HTML: pass.
- External link check: 10/10 URLs returned `200`.
- Forbidden secret/private-address scan: pass.
- Browser checks at 360, 390, 768, and 1440 CSS pixels: no horizontal overflow.
- Browser checks: one `h1`, titled lazy iframe, all external links use `noopener noreferrer`, and no page errors.
- Public desktop and mobile screenshots captured for visual inspection: pass.
- Bilibili player loads when the demo section enters the viewport: pass.

## Product regression

- Backend: `388 passed, 1 skipped` in `935.04s`.
- Frontend: `153 passed`, typecheck pass, production build pass.
- Main `backend` and `frontend` GitHub Actions checks: success.

## Evidence boundaries

The public page reports only values with repository evidence. The `$0.264697` figure is identified as a measured run cost under the recorded 2026-09-12 pricing assumptions, not a general production price. The Haystack regression and upstream comparison are described as specific public cases, not universal outcomes.