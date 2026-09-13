# GitHub Webhook Integration

EvalPilot can write a release-gate summary directly to a pull request.

## Configuration

```text
EVALPILOT_GITHUB_WEBHOOK_SECRET
EVALPILOT_GITHUB_TOKEN
EVALPILOT_GITHUB_API_URL
```

- The webhook secret verifies `X-Hub-Signature-256`.
- The token needs permission to comment on issues in the target repository.
- The API URL defaults to `https://api.github.com` and can point at GitHub
  Enterprise.

## Webhook endpoint

```text
POST /api/integrations/github/webhook
```

The receiver accepts repository-dispatch payloads:

```json
{
  "repository": {"full_name": "acme/assistant"},
  "client_payload": {
    "run_id": "completed-evalpilot-run",
    "pr_number": 42
  }
}
```

It also accepts a pull-request webhook with `run_id` at the top level.

The response includes:

```json
{
  "accepted": true,
  "decision": "block",
  "exit_code": 2,
  "comment_url": "https://github.com/acme/assistant/pull/42#issuecomment-...",
  "commented": true
}
```

## Security

- The raw request body is verified before JSON parsing.
- Invalid signatures return `401`.
- A missing webhook secret returns `503`.
- A missing GitHub token returns `503` only when a PR comment is requested.
- No secret is returned by the API or written to evidence.
