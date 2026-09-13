"""HTTP contract for evaluating an external system under test (SUT).

The adapter is intentionally boring: EvalPilot posts one case to
``POST {base_url}/v1/answer`` and normalises the response into the same
``ExecutionResult`` shape the deterministic executor returns. A service written
in any language can implement the contract without importing EvalPilot.

When ``EVALPILOT_SUT_OFFLINE=true`` the adapter never opens a socket. It reads
the response from its content-addressed cache or fails loudly on a cache miss.
Cache keys cover only the semantic request (service, scenario, question,
version and intervention); run and case ids are execution identity, not SUT
inputs, so the same evaluation can be replayed offline under a new run id.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from evalpilot.clock import new_id, utc_now
from evalpilot.executor import ExecutionResult
from evalpilot.models import Evidence, TestCase


class SutError(RuntimeError):
    """The external SUT contract could not be satisfied."""


class SutRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    test_case_id: str
    scenario_id: str
    question: str
    version: str
    intervention: str | None = None


class SutResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str
    citations: list[str] = Field(default_factory=list)
    tool_calls: list[str] = Field(default_factory=list)
    latency_ms: int = Field(default=0, ge=0)
    model: str
    refused: bool = False


class HttpCaseExecutor:
    """Execute one EvalPilot case against an HTTP service under test."""

    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float = 20.0,
        offline: bool = False,
        cache_dir: Path | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.offline = offline
        self.cache_dir = cache_dir
        self._transport = transport
        if self.cache_dir is not None:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def execute(
        self,
        case: TestCase,
        registry: Any,
        db: Any,
        intervention: str | None = None,
    ) -> ExecutionResult:
        del registry  # Kept for signature compatibility with the mock executor.
        request = SutRequest(
            run_id=case.run_id,
            test_case_id=case.id,
            scenario_id=str(case.input.get("scenario_id", "")),
            question=str(case.input.get("question", "")),
            version=str(case.input.get("version_label") or case.version),
            intervention=intervention,
        )
        response = self._answer(request)
        created_at = utc_now()
        base = {"run_id": case.run_id, "test_case_id": case.id, "created_at": created_at}
        trace_uri = db.write_artifact(
            case.run_id,
            f"{case.id}-sut-trace.json",
            json.dumps(
                {
                    "request": request.model_dump(mode="json"),
                    "response": response.model_dump(mode="json"),
                },
                indent=2,
                ensure_ascii=False,
            ),
        )

        evidence = [
            Evidence(
                id=new_id(),
                kind="citation",
                uri=uri,
                payload={"uri": uri},
                **base,
            )
            for uri in response.citations
        ]
        evidence.extend(
            [
                Evidence(
                    id=new_id(),
                    kind="trace",
                    uri=trace_uri,
                    payload={
                        "tool_calls": list(response.tool_calls),
                        "request": request.model_dump(mode="json"),
                        "response_model": response.model,
                    },
                    **base,
                ),
                Evidence(
                    id=new_id(),
                    kind="text",
                    uri=None,
                    payload={
                        "answer": response.answer,
                        "question": request.question,
                        "refused": response.refused,
                    },
                    **base,
                ),
                Evidence(
                    id=new_id(),
                    kind="metric",
                    uri=None,
                    payload={
                        "latency_ms": response.latency_ms,
                        "citation_count": len(response.citations),
                        "refused": response.refused,
                    },
                    **base,
                ),
            ]
        )
        output = {
            "scenario_id": request.scenario_id,
            "version": request.version,
            "model": response.model,
            "answer": response.answer,
            "citations": list(response.citations),
            "refused": response.refused,
            "latency_ms": response.latency_ms,
            "tool_calls": list(response.tool_calls),
            "intervention": intervention,
        }
        return ExecutionResult(output=output, evidence=evidence)

    def _answer(self, request: SutRequest) -> SutResponse:
        cache_path = self._cache_path(request)
        if cache_path is not None and cache_path.exists():
            try:
                return SutResponse.model_validate_json(cache_path.read_text(encoding="utf-8"))
            except (OSError, ValidationError, ValueError) as exc:
                raise SutError(f"SUT cache entry is invalid: {cache_path}") from exc

        if self.offline:
            raise SutError(
                "offline SUT cache miss; refusing to open a network connection"
            )

        url = f"{self.base_url}/v1/answer"
        try:
            with httpx.Client(
                timeout=self.timeout_seconds,
                transport=self._transport,
            ) as client:
                response = client.post(url, json=request.model_dump(mode="json"))
        except httpx.HTTPError as exc:
            raise SutError(f"SUT request failed: {exc}") from exc

        if response.status_code >= 400:
            raise SutError(
                f"SUT returned HTTP {response.status_code}: {response.text[:500]}"
            )
        try:
            parsed = SutResponse.model_validate(response.json())
        except (ValueError, ValidationError) as exc:
            raise SutError(f"SUT response violates the contract: {exc}") from exc

        if cache_path is not None:
            cache_path.write_text(
                parsed.model_dump_json(indent=2),
                encoding="utf-8",
            )
        return parsed

    def _cache_path(self, request: SutRequest) -> Path | None:
        if self.cache_dir is None:
            return None
        # Run and case ids identify an execution, not the SUT input. Excluding
        # them lets a later run replay the same scenarios from cache offline.
        payload = json.dumps(
            {
                "base_url": self.base_url,
                "scenario_id": request.scenario_id,
                "question": request.question,
                "version": request.version,
                "intervention": request.intervention,
            },
            sort_keys=True,
            ensure_ascii=True,
        ).encode("utf-8")
        return self.cache_dir / f"{hashlib.sha256(payload).hexdigest()}.json"
