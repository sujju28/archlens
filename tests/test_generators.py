from archlens.generators.markdown_report import MarkdownReportGenerator
from archlens.generators.mermaid import MermaidGenerator
from archlens.generators.structurizr import StructurizrExporter
from archlens.models import ArchElement, ArchRelationship, ArchSnapshot


def _snap():
    return ArchSnapshot(
        snapshot_id="s",
        commit_sha="x",
        repo_path="/tmp",
        metadata={"project_name": "Demo"},
        elements=[
            ArchElement(id="c.UserController", name="UserController", stereotype="Controller", language="java", file_path="api/UserController.java"),
            ArchElement(id="c.UserService", name="UserService", stereotype="Service", language="java", file_path="svc/UserService.java"),
        ],
        relationships=[
            ArchRelationship(source_id="c.UserController", target_id="c.UserService", rel_type="injects"),
        ],
    )


def test_mermaid_component_diagram():
    out = MermaidGenerator().generate(_snap(), level="component")
    assert "graph LR" in out
    assert "UserController" in out
    assert "UserService" in out
    assert "-->" in out


def test_mermaid_respects_max_edges():
    elements = [
        ArchElement(
            id=f"c.C{i}",
            name=f"C{i}",
            stereotype="Component",
            language="java",
            file_path=f"p/C{i}.java",
        )
        for i in range(10)
    ]
    elements.append(
        ArchElement(
            id="c.Svc",
            name="Svc",
            stereotype="Service",
            language="java",
            file_path="p/Svc.java",
        )
    )
    relationships = [
        ArchRelationship(source_id=f"c.C{i}", target_id=f"c.C{(i + 1) % 10}", rel_type="calls")
        for i in range(10)
    ]
    relationships.append(
        ArchRelationship(source_id="c.Svc", target_id="c.C0", rel_type="uses")
    )
    snap = ArchSnapshot(
        snapshot_id="s",
        commit_sha="x",
        repo_path="/tmp",
        metadata={},
        elements=elements,
        relationships=relationships,
    )
    out = MermaidGenerator(max_edges=3).generate(snap, level="component")
    edge_lines = [ln for ln in out.splitlines() if "-->" in ln]
    assert len(edge_lines) == 3
    assert "Svc" in out
    assert "truncated" in out


def test_report_skips_huge_component_mermaid(tmp_path):
    elements = [
        ArchElement(
            id=f"c.E{i}",
            name=f"E{i}",
            stereotype="Component",
            language="java",
            file_path=f"app/E{i}.java",
        )
        for i in range(6)
    ]
    relationships = [
        ArchRelationship(source_id=f"c.E{i}", target_id=f"c.E{(i + 1) % 6}", rel_type="calls")
        for i in range(6)
    ]
    snap = ArchSnapshot(
        snapshot_id="s",
        commit_sha="x",
        repo_path="/tmp",
        metadata={"project_name": "Big"},
        elements=elements,
        relationships=relationships,
    )
    mmd = tmp_path / "architecture" / "components.mmd"
    md = MarkdownReportGenerator(max_edges=2).generate(
        snap,
        component_diagram_path=mmd,
        component_diagram_relpath="architecture/components.mmd",
    )
    assert "## Container Diagram" in md
    assert "Not embedded" in md
    assert "architecture/components.mmd" in md
    assert "## Solution shape" in md
    assert "## Containers (modules)" in md
    assert md.count("```mermaid") >= 2  # context + container
    assert mmd.exists()
    assert sum(1 for ln in mmd.read_text().splitlines() if "-->" in ln) == 6


def test_report_includes_entry_points_and_health():
    snap = _snap()
    md = MarkdownReportGenerator().generate(snap)
    assert "## API & entry points" in md
    assert "UserController" in md
    assert "## Architecture health" in md
    assert "## Stereotype Summary" in md


def test_mermaid_unlimited_export():
    elements = [
        ArchElement(
            id=f"c.E{i}",
            name=f"E{i}",
            stereotype="Component",
            language="java",
            file_path=f"app/E{i}.java",
        )
        for i in range(5)
    ]
    relationships = [
        ArchRelationship(source_id=f"c.E{i}", target_id=f"c.E{(i + 1) % 5}", rel_type="calls")
        for i in range(5)
    ]
    snap = ArchSnapshot(
        snapshot_id="s",
        commit_sha="x",
        repo_path="/tmp",
        metadata={},
        elements=elements,
        relationships=relationships,
    )
    out = MermaidGenerator(max_edges=0).generate(snap, level="component")
    assert sum(1 for ln in out.splitlines() if "-->" in ln) == 5
    assert "truncated" not in out


def test_structurizr_export():
    out = StructurizrExporter().generate(_snap())
    assert "workspace" in out
    assert "UserController" in out
