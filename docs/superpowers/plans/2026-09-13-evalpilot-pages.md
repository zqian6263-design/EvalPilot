# EvalPilot Public Pages Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish a fast, Chinese-language, evidence-first EvalPilot product site on GitHub Pages.

**Architecture:** A dependency-free static site in `site/` is validated by `scripts/check-site.ps1`, packaged directly by GitHub Actions, and published with the official Pages deployment chain. Existing API, frontend, and product behavior remain unchanged.

**Tech Stack:** Semantic HTML5, CSS, inline SVG, PowerShell verification, GitHub Actions Pages.

**Spec:** `docs/superpowers/specs/2026-09-13-evalpilot-pages-design.md`

## Global Constraints

- Chinese-first, light, minimal enterprise presentation.
- No framework, package manager, runtime JavaScript, analytics, cookies, or third-party fonts.
- Only `https://player.bilibili.com/player.html?...` is a third-party runtime embed.
- Public claims must link to `README.md`, `PRODUCT.md`, or `docs/` evidence.
- Never claim customer adoption, interviews, paid pilots, market share, or roadmap capabilities.
- External links use `rel="noopener noreferrer"`.
- No secrets, `localhost`, `127.0.0.1`, raw IPs, or private paths in `site/`.
- Production URL: `https://zqian6263-design.github.io/EvalPilot/`.
- Official action versions verified upstream on 2026-09-13: `checkout@v7`, `configure-pages@v6`, `upload-pages-artifact@v5`, `deploy-pages@v5`.
- Existing backend, frontend, and E2E behavior must remain green.

---

### Task 1: Add the static-site acceptance checker

**Files:**
- Create: `scripts/check-site.ps1`

**Interfaces:**
- Consumes: the future `site/` directory and workflow-controlled repository layout.
- Produces: exit code `0` when all structural, claim, security, and internal-link checks pass; exit code `1` with every violation printed otherwise.

- [ ] **Step 1: Write the failing checker**

Create a PowerShell script that:

1. Resolves the repository root from `$PSScriptRoot`.
2. Requires `index.html`, `styles.css`, `favicon.svg`, `robots.txt`, `sitemap.xml`, and `404.html`.
3. Requires exactly one `<h1>` and section ids `product`, `loop`, `evidence`, `architecture`, `start`, `demo`.
4. Requires the evidence strings `8 / 26`, `52 / 0`, `4 / 4`, `$0.264697`, `BLOCK / REVIEW / ALLOW`, `不会静默回退 mock`, the Bilibili URL, and the GitHub URL.
5. Requires `lang="zh-CN"`, meta description, canonical URL, and the Bilibili player URL.
6. Rejects `<script>`, analytics tokens, `localhost`, private addresses, common token prefixes, and absolute Windows paths.
7. Resolves every relative `href` and `src`, failing on missing files.
8. Prints all failures and exits `1`; otherwise prints `Site checks passed.` and exits `0`.

- [ ] **Step 2: Run the failing check**

Run: `pwsh -NoProfile -File .\scripts\check-site.ps1`

Expected: exit code `1` with six missing-file failures.

- [ ] **Step 3: Commit the checker**

```powershell
git add scripts/check-site.ps1
git commit -m "test: add public site acceptance checks"
```

### Task 2: Build the main product page

**Files:**
- Create: `site/index.html`
- Create: `site/styles.css`
- Create: `site/favicon.svg`
- Test: `scripts/check-site.ps1`

**Interfaces:**
- Consumes: EvalPilot facts and links already present in `README.md`, `PRODUCT.md`, and `docs/`.
- Produces: one static document with sections `product`, `problem`, `loop`, `evidence`, `architecture`, `demo`, `start`, plus its stylesheet and favicon.

- [ ] **Step 1: Implement the complete HTML contract**

The page must contain, in order:

```text
skip link
sticky brand/nav header
hero: positioning, problem, value, video CTA, GitHub CTA, Release link, four-step quality card
problem: three release-risk cards
loop: 26 matched scenarios, statistics, counterfactual replay, release gate
evidence: 8/26, 52/0, 4/4, 52 calls / $0.264697 with source links
architecture: brief -> planning -> SUT -> evidence -> statistics -> investigation -> replay -> gate
boundaries: loud SUT failure, bounded LLM authority, offline deterministic demo
demo: lazy Bilibili iframe plus direct link
quick start: Release link and copyable clone/deploy commands
final CTA and footer: GitHub, Release, License, Security
```

Use `<h1>` once. Use `<h2>` for major sections and `<h3>` for cards. Keep all user-visible copy concise and Chinese-first. Use exact evidence values and limitations from the spec. Do not add unsupported customer or commercial claims.

- [ ] **Step 2: Implement the visual system**

Create `site/styles.css` using the exact tokens from the spec:

```css
:root {
  color-scheme: light;
  --bg: #f6f8fb;
  --surface: #ffffff;
  --surface-muted: #eef2f7;
  --text: #182230;
  --muted: #475467;
  --border: #dfe3e8;
  --accent: #165dff;
  --accent-soft: #eaf1ff;
  --danger: #b42318;
  --radius: 12px;
}
```

Requirements:

- maximum content width `1120px`; responsive 3/4/2-column grids;
- `44px` minimum interactive height; visible `:focus-visible`;
- sticky white header, one-pixel borders, restrained shadow only on cards;
- 16px body, 1.65 line height, compact mobile typography;
- horizontal architecture strip only on narrow screens;
- Bilibili iframe at 16:9 with lazy loading;
- single-column layout below 640px; no horizontal page scroll at 360px;
- `prefers-reduced-motion` overrides;
- no gradients, neon glow, particle effects, or decorative animation.

- [ ] **Step 3: Add `site/favicon.svg`**

Use a blue rounded square, a white shield/pilot outline, and three white horizontal evidence lines. Keep the SVG standalone, small, and readable at 16px.

- [ ] **Step 4: Run the checker**

Run: `pwsh -NoProfile -File .\scripts\check-site.ps1`

Expected: only the three missing support-file failures until Task 3; no HTML, claim, secret, or internal-link failure.

- [ ] **Step 5: Commit the main page**

```powershell
git add site/index.html site/styles.css site/favicon.svg
git commit -m "feat: add EvalPilot public product page"
```

### Task 3: Add crawl metadata and a useful 404 page

**Files:**
- Create: `site/robots.txt`
- Create: `site/sitemap.xml`
- Create: `site/404.html`
- Modify: `site/styles.css`
- Test: `scripts/check-site.ps1`

**Interfaces:**
- Consumes: production URL from the spec.
- Produces: crawler metadata and a static fallback page that links to the site root, GitHub, and Release.

- [ ] **Step 1: Create exact metadata files**

`site/robots.txt`:

```text
User-agent: *
Allow: /
Sitemap: https://zqian6263-design.github.io/EvalPilot/sitemap.xml
```

`site/sitemap.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://zqian6263-design.github.io/EvalPilot/</loc></url>
</urlset>
```

- [ ] **Step 2: Create `site/404.html`**

Use the same language, favicon, stylesheet, header/button classes, and visual system as the main page. Include noindex, a single `<h1>`, a short explanation, and buttons for site root, GitHub, and Release.

- [ ] **Step 3: Add fallback styles**

Add a centered `.not-found` panel with a minimum viewport height, readable muted paragraph, and the existing button actions. Keep it single-column on mobile.

- [ ] **Step 4: Run the checker**

Run: `pwsh -NoProfile -File .\scripts\check-site.ps1`

Expected: `Site checks passed.`

- [ ] **Step 5: Commit metadata and fallback page**

```powershell
git add site/robots.txt site/sitemap.xml site/404.html site/styles.css
git commit -m "feat: add product site metadata and 404"
```
### Task 4: Add GitHub Pages deployment and public entry points

**Files:**
- Create: `.github/workflows/pages.yml`
- Modify: `README.md` after the license badge
- Modify: `docs/superpowers/specs/2026-09-13-evalpilot-pages-design.md` status line

**Interfaces:**
- Consumes: validated `site/` artifact and confirmed official Pages actions.
- Produces: automatic deployment on `main` and visible README/spec links.

- [ ] **Step 1: Create `.github/workflows/pages.yml`**

```yaml
name: Pages

on:
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: pages-${{ github.ref }}
  cancel-in-progress: true

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - name: Validate static site
        shell: pwsh
        run: ./scripts/check-site.ps1
      - uses: actions/configure-pages@v6
      - uses: actions/upload-pages-artifact@v5
        with:
          path: site
  deploy:
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    runs-on: ubuntu-latest
    needs: build
    steps:
      - name: Deploy to GitHub Pages
        id: deployment
        uses: actions/deploy-pages@v5
```

- [ ] **Step 2: Add the public link to README**

Insert immediately after the License badge:

```markdown
[![产品站](https://img.shields.io/badge/在线产品站-GitHub_Pages-165dff)](https://zqian6263-design.github.io/EvalPilot/)
```

Insert immediately before `## 当前状态`:

```markdown
公开产品站：<https://zqian6263-design.github.io/EvalPilot/>
```

- [ ] **Step 3: Mark the spec approved**

Change the status line to:

```markdown
Status: Approved and implemented
```

- [ ] **Step 4: Run the checker and inspect the workflow**

Run:

```powershell
pwsh -NoProfile -File .\scripts\check-site.ps1
git diff --check
```

Expected: `Site checks passed.` and no whitespace errors.

- [ ] **Step 5: Commit deployment files**

```powershell
git add .github/workflows/pages.yml README.md docs/superpowers/specs/2026-09-13-evalpilot-pages-design.md
git commit -m "ci: deploy public product site"
```

### Task 5: Verify local rendering and accessibility

**Files:**
- Test only: `site/`
- Generated evidence: `.runtime/pages-local-desktop.png`
- Generated evidence: `.runtime/pages-local-mobile.png`
- Generated evidence: `.runtime/pages-link-check.txt`

**Interfaces:**
- Consumes: completed `site/`.
- Produces: local HTTP, screenshot, link, secret, and responsive-layout evidence before publication.

- [ ] **Step 1: Run structural and HTTP checks**

Run:

```powershell
pwsh -NoProfile -File .\scripts\check-site.ps1
$job = Start-Job { python -m http.server 4173 --directory site }
try {
  Start-Sleep -Seconds 2
  $response = Invoke-WebRequest -Uri http://127.0.0.1:4173/ -UseBasicParsing
  "STATUS=$($response.StatusCode) LENGTH=$($response.Content.Length)"
} finally {
  Stop-Job $job
  Remove-Job $job
}
```

Expected: `STATUS=200` and body length greater than `10000`.

- [ ] **Step 2: Check external URLs with GET**

Run GET checks for the Bilibili video, player iframe base, GitHub repository, Release, four evidence files, LICENSE, and SECURITY. Record status codes to `.runtime/pages-link-check.txt`.

Expected: every URL returns `200` or an authenticated-player redirect that resolves to `200`.

- [ ] **Step 3: Produce desktop and mobile screenshots**

Start `python -m http.server 4173 --directory site` and capture:

- `.runtime/pages-local-desktop.png` at `1440x900`;
- `.runtime/pages-local-mobile.png` at `390x844`.

Use an installed Chromium-family browser in headless mode. Visually inspect both screenshots for clipping, overlap, unreadable text, unwanted horizontal scroll, and misleading visual emphasis.

- [ ] **Step 4: Verify no forbidden content**

Run:

```powershell
rg -n "sk-[A-Za-z0-9]|ghp_[A-Za-z0-9]|D:\\|C:\\|localhost" site
```

Expected: no match.

- [ ] **Step 5: Commit any visual fixes**

```powershell
git add site scripts/check-site.ps1
git commit -m "fix: polish public site rendering"
```

If no files changed, skip this commit.

### Task 6: Publish and verify public availability

**Files:**
- Modify through GitHub API: repository Homepage
- Create: `docs/PAGES_VERIFICATION.md`

**Interfaces:**
- Consumes: green CI, green Pages workflow, and public production URL.
- Produces: GitHub Pages enabled, Homepage updated, and a durable verification record.

- [ ] **Step 1: Push implementation and watch workflows**

Run: `git push origin main`

Expected: CI and Pages workflows start for the pushed commit.

- [ ] **Step 2: Enable and verify GitHub Pages with workflow source**

Use GitHub CLI if available; otherwise use the GitHub REST API. Required final setting is `build_type: workflow`. Do not print or persist any token in command output.

- [ ] **Step 3: Wait for successful deployment**

Verify the Pages workflow concludes `success` and its deployment URL is `https://zqian6263-design.github.io/EvalPilot/`.

- [ ] **Step 4: Verify the public page**

Run:

```powershell
$response = Invoke-WebRequest -Uri https://zqian6263-design.github.io/EvalPilot/ -UseBasicParsing -MaximumRedirection 5
"STATUS=$($response.StatusCode) LENGTH=$($response.Content.Length)"
$response.Content | Select-String -Pattern 'AI 应用回归评测与自主发布质量官','8 / 26','BV1mPYY6sE1k'
```

Expected: HTTP `200`, body greater than `10000`, and all required strings present.

- [ ] **Step 5: Update repository Homepage**

Set `homepageUrl` to `https://zqian6263-design.github.io/EvalPilot/` through the authenticated GitHub API. Confirm by reading repository metadata without exposing credentials.

- [ ] **Step 6: Record verification**

Create `docs/PAGES_VERIFICATION.md` containing:

```markdown
# Public Pages Verification

Date: 2026-09-13

- Production URL: https://zqian6263-design.github.io/EvalPilot/
- Local desktop screenshot: pass
- Local mobile screenshot: pass
- Structural checker: pass
- External link check: pass
- GitHub Pages workflow: pass
- Public HTTP status: 200
- Repository Homepage: updated
- Existing backend/frontend/E2E regression: pass
```

Replace every `pass` only after the corresponding evidence exists.

- [ ] **Step 7: Commit the verification record and push**

```powershell
git add docs/PAGES_VERIFICATION.md
git commit -m "docs: verify public product site"
git push origin main
```

Expected: final push triggers a second successful Pages deployment and leaves `main` clean and synchronized.
