"""GitHub webhook verification and API client."""

from __future__ import annotations

import hashlib
import hmac

import httpx


class GitHubError(RuntimeError):
    """A GitHub API operation failed."""


def verify_webhook_signature(body: bytes, signature: str | None, secret: str) -> bool:
    """Verify GitHub's ``X-Hub-Signature-256`` header."""

    if not signature or not signature.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    received = signature.removeprefix("sha256=")
    return hmac.compare_digest(expected, received)


class GitHubClient:
    """Minimal GitHub API client needed by the release-gate webhook."""

    def __init__(
        self,
        *,
        token: str,
        api_url: str = "https://api.github.com",
        timeout_seconds: float = 20.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.token = token
        self.api_url = api_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._transport = transport

    def comment_on_pull_request(self, repository: str, number: int, body: str) -> str:
        url = f"{self.api_url}/repos/{repository}/issues/{number}/comments"
        try:
            with httpx.Client(
                timeout=self.timeout_seconds,
                transport=self._transport,
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            ) as client:
                response = client.post(url, json={"body": body})
        except httpx.HTTPError as exc:
            raise GitHubError(f"GitHub API request failed: {exc}") from exc
        if response.status_code >= 400:
            raise GitHubError(
                f"GitHub API returned HTTP {response.status_code}: {response.text[:500]}"
            )
        payload = response.json()
        return str(payload.get("html_url") or "")


__all__ = ["GitHubClient", "GitHubError", "verify_webhook_signature"]
