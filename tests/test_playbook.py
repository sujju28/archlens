"""Reading path + change playbook tests."""

from pathlib import Path

from archlens.analysis.capabilities import Capability, CapabilityCatalog
from archlens.analysis.playbook import build_playbook, playbooks_for_catalog
from archlens.models import ArchElement, ArchRelationship, ArchSnapshot


def test_playbook_reading_path_and_excerpt(tmp_path: Path):
    src = tmp_path / "UserController.java"
    src.write_text(
        "package demo;\n"
        "/** Handles user account updates. */\n"
        "public class UserController {}\n",
        encoding="utf-8",
    )
    svc = tmp_path / "UserService.java"
    svc.write_text("public class UserService { /* persist users */ }\n", encoding="utf-8")
    testf = tmp_path / "test_user.py"
    testf.write_text("def test_usercontroller():\n    assert True\n", encoding="utf-8")

    snap = ArchSnapshot(
        snapshot_id="s",
        commit_sha="a",
        repo_path=str(tmp_path),
        elements=[
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
        ],
        relationships=[
            ArchRelationship(source_id="C", target_id="S", rel_type="injects"),
            ArchRelationship(source_id="S", target_id="E", rel_type="injects"),
        ],
        metadata={"project_name": "Demo"},
    )
    cap = Capability(
        id="usercontroller",
        title="Manage users",
        stereotype="Controller",
        elements=["UserController"],
        related_tables=["users"],
        owner="team-id",
    )
    pb = build_playbook(snap, cap, repo=tmp_path)
    names = [s.name for s in pb.reading_path]
    assert names[0] == "UserController"
    assert "UserService" in names
    assert "User" in names
    assert pb.reading_path[0].excerpt
    assert "Handles user" in pb.reading_path[0].excerpt
    assert "users" in pb.tables
    assert any("test_user" in t for t in pb.tests)
    md = pb.to_markdown()
    assert "Start here" in md
    assert "Blast radius" in md or "Suggested" in md


def test_playbooks_filter_by_capability_id():
    snap = ArchSnapshot(
        snapshot_id="s",
        commit_sha="a",
        repo_path="/tmp",
        elements=[
            ArchElement(
                id="A",
                name="OrderController",
                stereotype="Controller",
                language="java",
                file_path="OrderController.java",
            )
        ],
    )
    catalog = CapabilityCatalog(
        capabilities=[
            Capability(
                id="ordercontroller",
                title="Orders",
                elements=["OrderController"],
                stereotype="Controller",
            ),
            Capability(
                id="other",
                title="Other",
                elements=["Nope"],
                stereotype="Controller",
            ),
        ]
    )
    books = playbooks_for_catalog(snap, catalog, repo="/tmp", capability_id="Orders")
    assert len(books) == 1
    assert books[0].capability_id == "ordercontroller"
