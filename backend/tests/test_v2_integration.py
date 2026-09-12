from __future__ import annotations

from fastapi.testclient import TestClient

from evalpilot.investigation.engine_provider import EngineCounterfactualProvider


def test_container_installs_the_measured_counterfactual_provider(
    client: TestClient,
) -> None:
    container = client.app.state.container
    assert isinstance(container.investigation_runner.provider, EngineCounterfactualProvider)
    assert container.investigation_runner.provider.name == "counterfactual-engine"
