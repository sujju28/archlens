from click.testing import CliRunner

from archlens.cli import cli


def test_cli_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "scan" in result.output
    assert "impact" in result.output
    assert "mcp" in result.output


def test_cli_init_and_scan(tmp_path):
    # Minimal python fixture
    svc = tmp_path / "services"
    svc.mkdir()
    (svc / "user_service.py").write_text(
        "class UserService:\n    pass\n",
        encoding="utf-8",
    )
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(cli, ["init", "--repo", str(tmp_path)])
    assert result.exit_code == 0
    assert (tmp_path / ".archlens").exists()
    assert (tmp_path / ".cursor" / "skills" / "archlens-onboard" / "SKILL.md").exists()
    assert (tmp_path / ".cursor" / "mcp.json").exists()

    result = runner.invoke(cli, ["scan", "--repo", str(tmp_path), "--commit", "abc"])
    assert result.exit_code == 0
    assert "Scan complete" in result.output

    result = runner.invoke(cli, ["diagram", "--repo", str(tmp_path), "--format", "mermaid"])
    assert result.exit_code == 0
    assert "graph" in result.output

    result = runner.invoke(cli, ["export", "--repo", str(tmp_path)])
    assert result.exit_code == 0
    assert "elements" in result.output
