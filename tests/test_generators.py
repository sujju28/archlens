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
    assert "injects" in out


def test_structurizr_export():
    out = StructurizrExporter().generate(_snap())
    assert "workspace" in out
    assert "UserController" in out
