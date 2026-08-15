"""Phase 3 tests: aggregation, events, contracts, health, federation."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from archlens.analysis.health import HealthScorer
from archlens.cli import cli
from archlens.distributed.aggregator import aggregate_snapshots
from archlens.distributed.events import EventFlowTracer
from archlens.distributed.openapi_linker import OpenAPIContractLinker
from archlens.mcp_tools import TOOL_SPECS, tool_aggregate, tool_health
from archlens.models import ArchElement, ArchRelationship, ArchSnapshot


def _snap(name: str, elements: list[ArchElement], rels: list[ArchRelationship] | None = None) -> ArchSnapshot:
    return ArchSnapshot(
        snapshot_id=f"s-{name}",
        commit_sha="abc",
        repo_path=f"/tmp/{name}",
        elements=elements,
        relationships=rels or [],
        metadata={"project_name": name},
    )


def test_aggregate_prefixes_ids():
    a = _snap(
        "billing",
        [ArchElement(id="UserService", name="UserService", stereotype="Service", language="java", file_path="UserService.java")],
    )
    b = _snap(
        "orders",
        [ArchElement(id="UserService", name="UserService", stereotype="Service", language="java", file_path="UserService.java")],
        [ArchRelationship(source_id="UserService", target_id="UserService", rel_type="calls")],
    )
    # self-call weird but tests remapping
    agg = aggregate_snapshots([a, b], system_name="Shop")
    ids = {e.id for e in agg.elements}
    assert "billing::UserService" in ids
    assert "orders::UserService" in ids
    assert agg.metadata["aggregated"] is True


def test_event_flow_kafka_detection(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "Producer.java").write_text(
        'public class Producer { void x(){ kafkaTemplate.send("orders.created", msg); } }\n',
        encoding="utf-8",
    )
    (src / "Consumer.java").write_text(
        '@KafkaListener(topics = "orders.created") public class Consumer {}\n',
        encoding="utf-8",
    )
    report = EventFlowTracer().scan_repo(tmp_path)
    assert "orders.created" in report.topics
    assert report.topics["orders.created"]["producers"]
    assert report.topics["orders.created"]["consumers"]
    assert report.relationships


def test_openapi_contract_linking(tmp_path: Path):
    api = tmp_path / "api-service"
    client = tmp_path / "web-service"
    api.mkdir()
    client.mkdir()
    (api / "openapi.json").write_text(
        json.dumps(
            {
                "openapi": "3.0.0",
                "paths": {
                    "/users/{id}": {
                        "get": {"operationId": "getUser"},
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    (client / "client.py").write_text(
        'import httpx\nhttpx.get("http://api-service/users/123")\n',
        encoding="utf-8",
    )
    report = OpenAPIContractLinker().analyze_repos([api, client])
    assert report.operations
    assert report.call_sites
    assert report.links
    assert any(l["method"] == "GET" for l in report.links)


def test_health_detects_cycle_and_layer_violation():
    snap = ArchSnapshot(
        snapshot_id="h1",
        commit_sha="x",
        repo_path="/tmp",
        elements=[
            ArchElement(id="C", name="C", stereotype="Controller", language="java", file_path="C.java"),
            ArchElement(id="S", name="S", stereotype="Service", language="java", file_path="S.java"),
            ArchElement(id="R", name="R", stereotype="Repository", language="java", file_path="R.java"),
        ],
        relationships=[
            ArchRelationship(source_id="C", target_id="S", rel_type="injects"),
            ArchRelationship(source_id="S", target_id="R", rel_type="injects"),
            ArchRelationship(source_id="R", target_id="C", rel_type="calls"),  # cycle + layer violation
            ArchRelationship(source_id="S", target_id="C", rel_type="calls"),  # layer violation
        ],
    )
    report = HealthScorer().analyze(snap)
    assert report.metrics["cycle_count"] >= 1
    assert report.metrics["layer_violation_count"] >= 1
    assert report.score < 100
    assert report.grade in {"A", "B", "C", "D", "F"}


def test_cli_phase3_commands(tmp_path: Path):
    # Build two tiny exports and aggregate
    e1 = tmp_path / "a.json"
    e2 = tmp_path / "b.json"
    s1 = _snap(
        "svc-a",
        [ArchElement(id="A", name="A", stereotype="Service", language="python", file_path="a.py")],
    )
    s2 = _snap(
        "svc-b",
        [ArchElement(id="B", name="B", stereotype="Service", language="python", file_path="b.py")],
    )
    e1.write_text(json.dumps(s1.model_dump(mode="json")), encoding="utf-8")
    e2.write_text(json.dumps(s2.model_dump(mode="json")), encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["aggregate", "--input", str(e1), "--input", str(e2), "--output", str(tmp_path / "out.json")],
    )
    assert result.exit_code == 0, result.output
    out = json.loads((tmp_path / "out.json").read_text(encoding="utf-8"))
    assert len(out["elements"]) == 2

    # health needs a local scan DB
    svc = tmp_path / "app" / "services"
    svc.mkdir(parents=True)
    (svc / "x.py").write_text("class XService:\n    pass\n", encoding="utf-8")
    assert runner.invoke(cli, ["init", "--repo", str(tmp_path)]).exit_code == 0
    assert runner.invoke(cli, ["scan", "--repo", str(tmp_path), "--commit", "t"]).exit_code == 0
    result = runner.invoke(cli, ["health", "--repo", str(tmp_path), "--output", str(tmp_path / "h.json")])
    assert result.exit_code == 0, result.output
    health = json.loads((tmp_path / "h.json").read_text(encoding="utf-8"))
    assert "score" in health

    result = runner.invoke(cli, ["events", "--repo", str(tmp_path)])
    assert result.exit_code == 0


def test_mcp_phase3_tool_specs():
    names = {t["name"] for t in TOOL_SPECS}
    assert {
        "archlens_aggregate",
        "archlens_events",
        "archlens_contracts",
        "archlens_health",
        "archlens_federate",
    }.issubset(names)
    assert callable(tool_aggregate)
    assert callable(tool_health)
