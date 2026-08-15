from pathlib import Path

from archlens.config import ArchLensConfig
from archlens.scanner import scan_repository


def test_scan_java_fixture(tmp_path: Path):
    src = Path(__file__).parent / "fixtures" / "java_spring"
    # Copy into a mini repo so .archlens is writable
    for f in src.glob("*.java"):
        (tmp_path / f.name).write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "pom.xml").write_text("<project></project>", encoding="utf-8")

    config = ArchLensConfig(project_name="JavaFixture", include=[""], exclude=[".archlens/"])
    snap = scan_repository(tmp_path, commit="test", config=config)
    assert len(snap.elements) >= 3
    stereotypes = {e.stereotype for e in snap.elements}
    assert "Controller" in stereotypes
    assert "Service" in stereotypes
    assert len(snap.relationships) >= 1
