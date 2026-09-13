# Security Policy

## Reporting a vulnerability

Do not open a public issue for a vulnerability involving credentials, webhook
signature bypass, arbitrary command execution, or private data exposure.

Send a private report to the repository owner through GitHub's security
advisory workflow. Include:

- affected commit or tag;
- reproduction steps;
- impact;
- whether a secret or external service was involved.

## Secret handling

- Never commit `EVALPILOT_LLM_API_KEY`, `EVALPILOT_GITHUB_TOKEN`, or
  `EVALPILOT_GITHUB_WEBHOOK_SECRET`.
- GitHub webhook requests are verified against the raw request body with
  HMAC SHA-256.
- The API never returns configured secrets.
- The optional Python tool is disabled by default.
- SUT HTTP access should be restricted to trusted hosts in production.

## Supported versions

Security fixes are applied to the latest `main` commit and the newest
`evalpilot-*` release tag.
