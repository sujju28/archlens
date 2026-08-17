"""Tests for Phase 4 recommendations: schema drift, intents, traces, domains, timeline, NL cites."""

from pathlib import Path

from archlens.analysis.data_model import build_canonical_data_model
from archlens.analysis.domains import slice_domains
from archlens.analysis.impact_analyzer import ImpactAnalyzer
from archlens.analysis.intents import (
    ArchitectureIntents,
    ForbiddenEdge,
    apply_intents,
    validate_intents,
)
from archlens.analysis.narrative_diff import narrative_diff
from archlens.analysis.nl_query import run_nl_query
from archlens.analysis.process_traces import build_process_traces
from archlens.analysis.relationship_resolver import RelationshipResolver
from archlens.analysis.schema_drift import analyze_schema_drift, parse_schema_files
from archlens.models import ArchElement, ArchRelationship, ArchSnapshot


def _snap(elements, relationships=None) -> ArchSnapshot:
    return ArchSnapshot(
        snapshot_id="s1",
        commit_sha="abc",
        repo_path="/tmp",
        elements=elements,
        relationships=relationships or [],
    )


def test_schema_drift_vs_cdm(tmp_path: Path):
    sql = tmp_path / "db" / "migration"
    sql.mkdir(parents=True)
    (sql / "V1__users.sql").write_text(
        """
        CREATE TABLE users (
          id INTEGER PRIMARY KEY,
          email VARCHAR(255),
          order_id INTEGER
        );
        CREATE TABLE orders (
          id INTEGER PRIMARY KEY,
          status VARCHAR(32)
        );
        """,
        encoding="utf-8",
    )
    elements = [
        ArchElement(
            id="User",
            name="User",
            stereotype="Entity",
            language="typescript",
            file_path="user.ts",
            metadata={"table_name": "users", "columns": ["id", "email"]},
        ),
        ArchElement(
            id="Extra",
            name="Extra",
            stereotype="Entity",
            language="java",
            file_path="Extra.java",
            metadata={"table_name": "widgets", "columns": ["id"]},
        ),
    ]
    snap = _snap(elements)
    report = analyze_schema_drift(snap, tmp_path)
    assert "orders" in [t.lower() for t in report.only_in_schema]
    assert "widgets" in [t.lower() for t in report.only_in_cdm]
    assert report.has_drift
    md = report.to_markdown().lower()
    assert "orders" in md and "widgets" in md


def test_parse_create_table_columns(tmp_path: Path):
    f = tmp_path / "schema.sql"
    f.write_text("CREATE TABLE foo (bar INT, baz TEXT);", encoding="utf-8")
    tables = parse_schema_files([f])
    assert tables[0].name.lower() == "foo"
    assert "bar" in [c.lower() for c in tables[0].columns]


def test_intents_forbidden_edge_and_override():
    elements = [
        ArchElement(
            id="Ui",
            name="OrderPage",
            stereotype="UI Component",
            language="typescript",
            file_path="ui/OrderPage.tsx",
        ),
        ArchElement(
            id="Repo",
            name="OrderRepository",
            stereotype="Repository",
            language="typescript",
            file_path="repo/OrderRepository.ts",
        ),
        ArchElement(
            id="Legacy",
            name="LegacyBatchRunner",
            stereotype="Component",
            language="java",
            file_path="LegacyBatchRunner.java",
        ),
    ]
    rels = [
        ArchRelationship(
            source_id="Ui", target_id="Repo", rel_type="calls", description="bad"
        )
    ]
    snap = _snap(elements, rels)
    intents = ArchitectureIntents(
        stereotype_overrides={"LegacyBatchRunner": "Worker"},
        forbidden_edges=[
            ForbiddenEdge(
                source="UI Component",
                target="Repository",
                reason="UI must not hit repos",
            )
        ],
        owners={"OrderRepository": "team-orders"},
    )
    apply_intents(snap, intents=intents)
    assert snap.elements[2].stereotype == "Worker"
    assert snap.elements[1].metadata.get("owner") == "team-orders"
    result = validate_intents(snap, intents=intents)
    assert result["violation_count"] >= 1
    assert not result["ok"]


def test_process_traces_controller_to_entity():
    elements = [
        ArchElement(
            id="C",
            name="UserController",
            stereotype="Controller",
            language="java",
            file_path="UserController.java",
        ),
        ArchElement(
            id="S",
            name="UserService",
            stereotype="Service",
            language="java",
            file_path="UserService.java",
        ),
        ArchElement(
            id="E",
            name="User",
            stereotype="Entity",
            language="java",
            file_path="User.java",
            metadata={"table_name": "users"},
        ),
    ]
    rels = [
        ArchRelationship(source_id="C", target_id="S", rel_type="injects"),
        ArchRelationship(source_id="S", target_id="E", rel_type="injects"),
    ]
    report = build_process_traces(_snap(elements, rels))
    assert report.stats["trace_count"] >= 1
    assert any("UserController" in t.path and "User" in t.path for t in report.traces)


def test_domain_slicing_by_container():
    elements = [
        ArchElement(
            id="a",
            name="BillingService",
            stereotype="Service",
            language="java",
            file_path="billing/BillingService.java",
            metadata={"container": "Billing"},
        ),
        ArchElement(
            id="b",
            name="InvoiceService",
            stereotype="Service",
            language="java",
            file_path="billing/InvoiceService.java",
            metadata={"container": "Billing"},
        ),
        ArchElement(
            id="c",
            name="CatalogService",
            stereotype="Service",
            language="java",
            file_path="catalog/CatalogService.java",
            metadata={"container": "Catalog"},
        ),
        ArchElement(
            id="d",
            name="ProductEntity",
            stereotype="Entity",
            language="java",
            file_path="catalog/Product.java",
            metadata={"container": "Catalog", "table_name": "product"},
        ),
    ]
    report = slice_domains(_snap(elements), min_size=1)
    names = {d.name for d in report.domains}
    assert "Billing" in names
    assert "Catalog" in names


def test_narrative_timeline():
    a = _snap(
        [
            ArchElement(
                id="A",
                name="OldService",
                stereotype="Service",
                language="java",
                file_path="Old.java",
            )
        ]
    )
    b = _snap(
        [
            ArchElement(
                id="B",
                name="NewController",
                stereotype="Controller",
                language="java",
                file_path="New.java",
            )
        ]
    )
    b.snapshot_id = "s2"
    b.commit_sha = "def"
    narr = narrative_diff(a, b)
    assert "Added" in narr["narrative"] or narr["summary"]["added_elements"] == 1
    assert "Architecture timeline" in narr["markdown"]


def test_nl_query_citations_and_where_is():
    snap = _snap(
        [
            ArchElement(
                id="UserService",
                name="UserService",
                stereotype="Service",
                language="java",
                file_path="services/UserService.java",
            )
        ]
    )
    result = run_nl_query(snap, "where is UserService")
    assert result["result_count"] == 1
    assert result["results"][0]["citation"].endswith("UserService")
    assert result.get("citations")


def test_nl_path_query():
    snap = _snap(
        [
            ArchElement(
                id="C",
                name="UserController",
                stereotype="Controller",
                language="java",
                file_path="C.java",
            ),
            ArchElement(
                id="S",
                name="UserService",
                stereotype="Service",
                language="java",
                file_path="S.java",
            ),
        ],
        [ArchRelationship(source_id="C", target_id="S", rel_type="injects")],
    )
    result = run_nl_query(snap, "how does UserController reach UserService")
    assert result["result_count"] >= 1
    assert "UserController" in result["results"][0]["path"]


def test_impact_suggestions_mention_entity_and_blast():
    snap = _snap(
        [
            ArchElement(
                id="UserController",
                name="UserController",
                stereotype="Controller",
                language="java",
                file_path="UserController.java",
                metadata={"container": "API"},
            ),
            ArchElement(
                id="User",
                name="User",
                stereotype="Entity",
                language="java",
                file_path="User.java",
                metadata={"critical_paths": ["Checkout"]},
            ),
        ],
        [ArchRelationship(source_id="UserController", target_id="User", rel_type="injects")],
    )
    report = ImpactAnalyzer().analyze(snap, elements=["User"], depth=2)
    joined = " ".join(report.suggested_changes)
    assert "Blast radius" in joined or "Entity" in joined
    assert "schema-drift" in joined or "critical path" in joined


def test_interface_impl_di_resolution():
    elements = [
        ArchElement(
            id="Ctrl",
            name="OrderController",
            stereotype="Controller",
            language="java",
            file_path="OrderController.java",
        ),
        ArchElement(
            id="ISvc",
            name="OrderService",
            stereotype="Component",
            language="java",
            file_path="OrderService.java",
        ),
        ArchElement(
            id="Impl",
            name="OrderServiceImpl",
            stereotype="Service",
            language="java",
            file_path="OrderServiceImpl.java",
            implements=["OrderService"],
        ),
    ]
    rels = [
        ArchRelationship(source_id="Ctrl", target_id="ISvc", rel_type="injects"),
        ArchRelationship(source_id="Impl", target_id="ISvc", rel_type="implements"),
    ]
    resolved = RelationshipResolver().resolve(elements, rels)
    assert any(
        r.source_id == "Ctrl" and r.target_id == "Impl" and "interface" in (r.technology or "")
        for r in resolved
    )


def test_cdm_builds_with_languages():
    snap = _snap(
        [
            ArchElement(
                id="U",
                name="User",
                stereotype="Entity",
                language="python",
                file_path="u.py",
                metadata={"table_name": "users", "columns": ["id"], "kind": "sqlalchemy"},
            )
        ]
    )
    cdm = build_canonical_data_model(snap)
    assert cdm.stats["entity_count"] == 1
    assert cdm.entities[0].language == "python"
