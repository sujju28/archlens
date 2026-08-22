"""Hybrid capability catalog: auto-seed + preserve curated fields."""

from pathlib import Path

from archlens.analysis.capabilities import (
    Capability,
    CapabilityCatalog,
    discover_capabilities,
    guess_title,
    merge_catalog,
    sync_capabilities,
)
from archlens.generators.markdown_report import MarkdownReportGenerator
from archlens.models import ArchElement, ArchRelationship, ArchSnapshot


def _snap(elements, rels=None) -> ArchSnapshot:
    return ArchSnapshot(
        snapshot_id="s1",
        commit_sha="abc",
        repo_path="/tmp/caps",
        elements=elements,
        relationships=rels or [],
        metadata={"project_name": "Caps Demo"},
    )


def test_guess_title_from_controller_and_cobol():
    assert guess_title("UserController", "Controller") == "User"
    assert guess_title("COACTUPC", "UI Component") == "COACTUPC"
    assert "batch" in guess_title("PostTran", "Batch Job").lower()


def test_discover_from_entry_points():
    snap = _snap(
        [
            ArchElement(
                id="C",
                name="UserController",
                stereotype="Controller",
                language="java",
                file_path="UserController.java",
            ),
            ArchElement(
                id="U",
                name="User",
                stereotype="Entity",
                language="java",
                file_path="User.java",
                metadata={"table_name": "users"},
            ),
            ArchElement(
                id="S",
                name="Helper",
                stereotype="Component",
                language="java",
                file_path="Helper.java",
            ),
        ],
        [ArchRelationship(source_id="C", target_id="U", rel_type="injects")],
    )
    found = discover_capabilities(snap)
    assert len(found) == 1
    assert found[0].id == "usercontroller"
    assert found[0].title == "User"
    assert found[0].status == "candidate"
    assert "users" in found[0].related_tables


def test_merge_preserves_human_fields_and_flags_missing():
    existing = CapabilityCatalog(
        capabilities=[
            Capability(
                id="usercontroller",
                source="curated",
                status="approved",
                title="Manage users",
                description="CRUD for users",
                owner="team-id",
                elements=["UserController"],
                stereotype="Controller",
            ),
            Capability(
                id="old-screen",
                source="auto",
                status="candidate",
                title="Gone",
                elements=["OldScreen"],
                stereotype="UI Component",
            ),
        ]
    )
    discovered = [
        Capability(
            id="usercontroller",
            title="User",
            stereotype="Controller",
            elements=["UserController"],
            file_path="api/UserController.java",
            related_tables=["users"],
        )
    ]
    merged = merge_catalog(existing, discovered)
    by_id = {c.id: c for c in merged.capabilities}
    kept = by_id["usercontroller"]
    assert kept.title == "Manage users"
    assert kept.description == "CRUD for users"
    assert kept.owner == "team-id"
    assert kept.status == "approved"
    assert kept.source == "curated"
    assert kept.file_path == "api/UserController.java"
    assert kept.missing_in_code is False
    gone = by_id["old-screen"]
    assert gone.missing_in_code is True


def test_sync_writes_yaml_and_report_section(tmp_path: Path):
    snap = _snap(
        [
            ArchElement(
                id="C",
                name="OrderController",
                stereotype="Controller",
                language="java",
                file_path="OrderController.java",
            )
        ]
    )
    snap.repo_path = str(tmp_path)
    catalog = sync_capabilities(snap, tmp_path, persist=True)
    yaml_path = tmp_path / ".archlens" / "capabilities.yaml"
    assert yaml_path.exists()
    assert any(c.id == "ordercontroller" for c in catalog.capabilities)
    md = MarkdownReportGenerator().generate(snap)
    assert "## Capabilities" in md
    assert "Order" in md
