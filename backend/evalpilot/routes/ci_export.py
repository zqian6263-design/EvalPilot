"""CI exports for a completed run: JUnit XML and SARIF 2.1.0."""

from __future__ import annotations

from io import StringIO
from xml.etree import ElementTree

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from evalpilot import __version__
from evalpilot.container import Container
from evalpilot.dependencies import get_container
from evalpilot.models import RunStatus
from evalpilot.repository import NotFoundError

router = APIRouter()


def _completed_report(run_id: str, container: Container):
    try:
        run = container.repo.get_run(run_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    try:
        report = container.repo.get_report(run_id)
    except NotFoundError as exc:
        raise HTTPException(
            status_code=409,
            detail=(
                f"run {run_id} is {run.status.value}; CI exports are available once "
                f"the run reaches {RunStatus.COMPLETED.value}"
            ),
        ) from exc
    return run, report


@router.get("/runs/{run_id}/junit", response_class=Response)
def get_junit(run_id: str, container: Container = Depends(get_container)) -> Response:
    """Return the run's findings as JUnit XML for CI test reporters."""

    run, report = _completed_report(run_id, container)
    findings = report.findings
    suite = ElementTree.Element(
        "testsuite",
        name=f"EvalPilot {run.baseline_version} -> {run.candidate_version}",
        tests=str(max(1, len(findings))),
        failures=str(len(findings)),
        errors="0",
        skipped="0",
        time="0",
    )
    properties = ElementTree.SubElement(suite, "properties")
    ElementTree.SubElement(properties, "property", name="run_id", value=run.id)
    ElementTree.SubElement(properties, "property", name="candidate_version", value=run.candidate_version)
    ElementTree.SubElement(properties, "property", name="report_summary", value=report.summary)

    if findings:
        for finding in findings:
            case = ElementTree.SubElement(
                suite,
                "testcase",
                classname=finding.severity,
                name=finding.title,
            )
            failure = ElementTree.SubElement(
                case,
                "failure",
                message=finding.description,
                type=finding.severity,
            )
            failure.text = (
                f"confidence={finding.confidence:.4f}\n"
                f"evidence_ids={','.join(finding.evidence_ids)}\n"
                f"recommendation={finding.recommendation or ''}"
            )
    else:
        ElementTree.SubElement(suite, "testcase", classname="info", name="release_gate")

    stream = StringIO()
    ElementTree.ElementTree(suite).write(stream, encoding="unicode", xml_declaration=False)
    return Response(
        content='<?xml version="1.0" encoding="UTF-8"?>\n' + stream.getvalue(),
        media_type="application/xml",
    )


@router.get("/runs/{run_id}/sarif")
def get_sarif(run_id: str, container: Container = Depends(get_container)) -> dict:
    """Return findings as SARIF 2.1.0 for code-scanning integrations."""

    run, report = _completed_report(run_id, container)
    evidence = container.repo.list_evidence(run_id)
    evidence_by_case: dict[str, str] = {}
    for item in evidence:
        if item.uri and item.test_case_id not in evidence_by_case:
            evidence_by_case[item.test_case_id] = item.uri

    severity_level = {
        "critical": "error",
        "high": "error",
        "medium": "warning",
        "low": "note",
        "info": "note",
    }
    results = []
    for finding in report.findings:
        uri = evidence_by_case.get(finding.test_case_id or "")
        result = {
            "ruleId": "evalpilot.release-regression",
            "level": severity_level.get(finding.severity, "warning"),
            "message": {"text": finding.description},
            "properties": {
                "run_id": run.id,
                "finding_id": finding.id,
                "severity": finding.severity,
                "confidence": finding.confidence,
                "evidence_ids": finding.evidence_ids,
                "recommendation": finding.recommendation,
            },
        }
        if uri:
            result["locations"] = [
                {"physicalLocation": {"artifactLocation": {"uri": uri}}}
            ]
        results.append(result)

    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "EvalPilot",
                        "version": __version__,
                        "informationUri": "https://github.com/",
                        "rules": [
                            {
                                "id": "evalpilot.release-regression",
                                "name": "Release regression",
                                "shortDescription": {
                                    "text": "A candidate version regressed against baseline."
                                },
                            }
                        ],
                    }
                },
                "results": results,
                "properties": {
                    "run_id": run.id,
                    "baseline_version": run.baseline_version,
                    "candidate_version": run.candidate_version,
                    "finding_count": len(report.findings),
                    "summary": report.summary,
                },
            }
        ],
    }


__all__ = ["get_junit", "get_sarif", "router"]
