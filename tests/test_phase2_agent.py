from pathlib import Path

from click.testing import CliRunner

from archlens.analysis.nl_query import run_nl_query, structured_query
from archlens.cli import cli
from archlens.mcp_tools import TOOL_SPECS, tool_diagram, tool_impact, tool_query, tool_scan
from archlens.models import ArchElement, ArchRelationship, ArchSnapshot
from archlens.setup_ai import ALL_PLATFORMS, generate_adapters


def _snap() -> ArchSnapshot:
    return ArchSnapshot(
        snapshot_id="s1",
        commit_sha="abc",
        repo_path="/tmp",
        elements=[
            ArchElement(
                id="UserController",
                name="UserController",
                stereotype="Controller",
                language="java",
                file_path="UserController.java",
            ),
            ArchElement(
                id="UserService",
                name="UserService",
                stereotype="Service",
                language="java",
                file_path="UserService.java",
            ),
            ArchElement(
                id="UserRepository",
                name="UserRepository",
                stereotype="Repository",
                language="java",
                file_path="UserRepository.java",
            ),
        ],
        relationships=[
            ArchRelationship(source_id="UserController", target_id="UserService", rel_type="injects"),
            ArchRelationship(source_id="UserService", target_id="UserRepository", rel_type="injects"),
        ],
    )


def test_nl_query_tier1_upstream():
    result = run_nl_query(_snap(), "what depends on UserService")
    assert result["tier"] == "tier1"
    assert any(r["name"] == "UserController" for r in result["results"])


def test_nl_query_tier1_stereotype():
    result = run_nl_query(_snap(), "list all services")
    assert result["tier"] == "tier1"
    assert result["result_count"] == 1
    assert result["results"][0]["name"] == "UserService"


def test_nl_query_tier2_entity():
    result = run_nl_query(_snap(), "Tell me about UserRepository please")
    assert result["tier"] == "tier2"
    assert any(r["name"] == "UserRepository" for r in result["results"])


def test_nl_query_tier3_fallback():
    result = run_nl_query(_snap(), "find circular dependencies across bounded contexts")
    assert result["tier"] == "tier3"
    assert "schema" in result


def test_structured_query_group_by():
    result = structured_query(_snap(), group_by="stereotype")
    assert result["result_count"] == 3


def test_setup_ai_all_platforms(tmp_path: Path):
    created = generate_adapters(tmp_path, ["all"], overwrite=True)
    paths = {str(p.relative_to(tmp_path)) for p in created}
    assert "AGENTS.md" in paths
    assert ".github/copilot-instructions.md" in paths
    assert ".cursorrules" in paths
    assert ".cursor/mcp.json" in paths
    assert ".cursor/rules/archlens.mdc" in paths
    assert ".cursor/skills/archlens-onboard/SKILL.md" in paths
    assert ".cursor/skills/archlens-architect/SKILL.md" in paths
    assert ".claude/skills/archlens-change/SKILL.md" in paths
    assert ".windsurfrules" in paths
    assert ".windsurf/mcp.json" in paths
    assert ".vscode/settings.json" in paths
    assert ".agents/skills/archlens/SKILL.md" in paths
    assert ALL_PLATFORMS == {
        "claude",
        "copilot",
        "cursor",
        "windsurf",
        "antigravity",
        "vscode",
    }


def test_mcp_tools_end_to_end(tmp_path: Path):
    import json

    # Minimal python fixture
    svc = tmp_path / "services"
    svc.mkdir()
    (svc / "user_service.py").write_text("class UserService:\n    pass\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")

    payload = json.loads(tool_scan(str(tmp_path), commit="t1"))
    assert payload["status"] == "success"
    assert payload["total_elements"] >= 1

    q = json.loads(tool_query(str(tmp_path), query="list all services"))
    assert q["result_count"] >= 1

    impact = json.loads(tool_impact(str(tmp_path), elements=["UserService"]))
    assert "risk_score" in impact

    diagram = tool_diagram(str(tmp_path), level="component")
    assert "graph" in diagram

    names = {t["name"] for t in TOOL_SPECS}
    assert "archlens_scan" in names
    assert "archlens_query" in names
    assert "archlens_impact" in names
    assert "archlens_health" in names
    assert len(TOOL_SPECS) >= 11


def test_cli_setup_ai_and_query(tmp_path: Path):
    svc = tmp_path / "services"
    svc.mkdir()
    (svc / "order_service.py").write_text("class OrderService:\n    pass\n", encoding="utf-8")
    runner = CliRunner()
    assert runner.invoke(cli, ["init", "--repo", str(tmp_path)]).exit_code == 0
    assert runner.invoke(cli, ["scan", "--repo", str(tmp_path), "--commit", "x"]).exit_code == 0
    result = runner.invoke(
        cli, ["query", "--repo", str(tmp_path), "--json", "list all services"]
    )
    assert result.exit_code == 0
    assert "tier" in result.output

    result = runner.invoke(cli, ["setup-ai", "--repo", str(tmp_path), "--platform", "all"])
    assert result.exit_code == 0
    assert (tmp_path / "AGENTS.md").exists()
    assert (tmp_path / ".cursor" / "mcp.json").exists()
    assert (tmp_path / ".cursor" / "skills" / "archlens-onboard" / "SKILL.md").exists()
    assert (tmp_path / ".windsurf" / "mcp.json").exists()
