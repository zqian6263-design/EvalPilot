"""GitHub webhook and client integration tests."""

from __future__ import annotations

import hashlib
import hmac
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from evalpilot.app import create_app
from evalpilot.integrations.github import GitHubClient, GitHubError, verify_webhook_signature

from .conftest import make_settings, start_and_wait


def _signed(body: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _completed_run(client: TestClient) -> tuple[str, str]:
    project = client.post(
        "/api/projects", json={"name": "GitHub webhook", "scenario": "kb-qa"}
    ).json()
    run = client.post(
        "/api/runs",
        json={
            "project_id": project["id"],
            "baseline_version": "v1.0-baseline",
            "candidate_version": "v1.1-candidate",
            "case_count": 26,
            "seed": 20260919,
        },
    ).json()
    detail = start_and_wait(client, run["id"])
    assert detail["run"]["status"] == "completed"
    return project["id"], run["id"]


def test_webhook_requires_configured_secret(tmp_path) -> None:
    with TestClient(create_app(make_settings(tmp_path))) as client:
        response = client.post("/api/integrations/github/webhook", json={})
    assert response.status_code == 503


def test_webhook_rejects_invalid_signature(tmp_path) -> None:
    settings = make_settings(tmp_path, github_webhook_secret="secret")
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/integrations/github/webhook",
            content=b"{}",
            headers={"X-Hub-Signature-256": "sha256=bad"},
        )
    assert response.status_code == 401


def test_webhook_posts_gate_comment_to_pull_request(
    tmp_path, monkeypatch
) -> None:
    settings = make_settings(
        tmp_path,
        github_webhook_secret="secret",
        github_token="token",
    )
    with TestClient(create_app(settings)) as client:
        _, run_id = _completed_run(client)
        payload = {
            "repository": {"full_name": "acme/assistant"},
            "client_payload": {"run_id": run_id, "pr_number": 42},
        }
        body = json.dumps(payload).encode()
        calls: list[tuple[str, int, str]] = []

        def fake_comment(self, repository: str, number: int, text: str) -> str:
            calls.append((repository, number, text))
            return "https://github.com/acme/assistant/pull/42#issuecomment-1"

        monkeypatch.setattr(GitHubClient, "comment_on_pull_request", fake_comment)
        response = client.post(
            "/api/integrations/github/webhook",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": _signed(body, "secret"),
            },
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["decision"] == "block"
    assert payload["exit_code"] == 2
    assert payload["commented"] is True
    assert calls and calls[0][0:2] == ("acme/assistant", 42)
    assert "EvalPilot Release Gate" in calls[0][2]


def test_signature_verification_is_exact() -> None:
    body = b'{"run_id":"r"}'
    signature = _signed(body, "secret")
    assert verify_webhook_signature(body, signature, "secret") is True
    assert verify_webhook_signature(body, signature, "other") is False
    assert verify_webhook_signature(body, None, "secret") is False


def test_github_client_sends_auth_and_returns_comment_url() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(201, json={"html_url": "https://github.com/c/1#issuecomment-2"})

    client = GitHubClient(
        token="secret-token",
        transport=httpx.MockTransport(handler),
    )
    url = client.comment_on_pull_request("acme/repo", 7, "gate body")
    assert url.endswith("#issuecomment-2")
    assert seen[0].url.path == "/repos/acme/repo/issues/7/comments"
    assert seen[0].headers["authorization"] == "Bearer secret-token"


def test_github_client_rejects_api_failure() -> None:
    client = GitHubClient(
        token="token",
        transport=httpx.MockTransport(lambda request: httpx.Response(403, text="forbidden")),
    )
    with pytest.raises(GitHubError, match="403"):
        client.comment_on_pull_request("acme/repo", 7, "body")
