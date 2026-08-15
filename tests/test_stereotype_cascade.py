"""Tests for multi-signal stereotype cascade and monorepo containers."""

from pathlib import Path

from archlens.config import ArchLensConfig, ContainerMapping, StereotypeMapping
from archlens.extractors.stereotype import resolve_stereotype
from archlens.generators.mermaid import MermaidGenerator
from archlens.models import ArchElement, ArchSnapshot
from archlens.scanner import scan_repository


def test_cascade_annotation_beats_naming():
    stereo = resolve_stereotype(
        language="java",
        name="UserService",  # would be Service by name
        file_path="src/UserService.java",
        annotations=["RestController"],
    )
    assert stereo == "Controller"


def test_cascade_inheritance_jpa_repository():
    stereo = resolve_stereotype(
        language="java",
        name="OrderDao",
        file_path="src/OrderDao.java",
        annotations=[],
        extends="JpaRepository",
    )
    assert stereo == "Repository"


def test_cascade_naming_service_impl():
    stereo = resolve_stereotype(
        language="java",
        name="UserServiceImpl",
        file_path="src/misc/UserServiceImpl.java",
        annotations=[],
    )
    assert stereo == "Service"


def test_cascade_directory_convention():
    stereo = resolve_stereotype(
        language="python",
        name="Thing",
        file_path="app/services/thing.py",
        annotations=[],
    )
    assert stereo == "Service"


def test_cascade_fallback_component():
    stereo = resolve_stereotype(
        language="python",
        name="Helper",
        file_path="utils/helper.py",
        annotations=[],
    )
    assert stereo == "Component"


def test_yaml_custom_annotation_override():
    config = ArchLensConfig(
        stereotypes={
            "java": [
                StereotypeMapping(annotation="BusinessLogic", stereotype="Service"),
            ]
        }
    )
    stereo = resolve_stereotype(
        language="java",
        name="Foo",
        file_path="src/Foo.java",
        annotations=["BusinessLogic"],
        config=config,
    )
    assert stereo == "Service"


def test_containers_mapping_on_scan(tmp_path: Path):
    api = tmp_path / "apps" / "api" / "services"
    api.mkdir(parents=True)
    (api / "user_service.py").write_text("class UserService:\n    pass\n", encoding="utf-8")
    web = tmp_path / "apps" / "web" / "components"
    web.mkdir(parents=True)
    (web / "UserCard.py").write_text("class UserCard:\n    pass\n", encoding="utf-8")

    config = ArchLensConfig(
        project_name="Mono",
        include=[""],
        exclude=[".archlens/"],
        containers=[
            ContainerMapping(path="apps/api/**", name="API Service"),
            ContainerMapping(path="apps/web/**", name="Web App"),
        ],
    )
    snap = scan_repository(tmp_path, commit="t", config=config, persist=False)
    containers = {e.name: e.metadata.get("container") for e in snap.elements}
    assert containers.get("UserService") == "API Service"
    assert containers.get("UserCard") == "Web App"

    diagram = MermaidGenerator().generate(snap, level="container")
    assert "API_Service" in diagram or "API Service" in diagram.replace("<br/>", " ")
    assert "Web_App" in diagram or "Web App" in diagram


def test_react_inheritance_ui_component():
    stereo = resolve_stereotype(
        language="typescript",
        name="Dashboard",
        file_path="src/Dashboard.tsx",
        annotations=[],
        extends="React.Component",
    )
    assert stereo == "UI Component"
