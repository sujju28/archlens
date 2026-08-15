from archlens.analysis.diff_engine import DiffEngine
from archlens.models import ArchElement, ArchSnapshot


def test_diff_detects_added_and_removed():
    a = ArchSnapshot(
        snapshot_id="a",
        commit_sha="1",
        repo_path="/tmp",
        elements=[
            ArchElement(id="A", name="A", stereotype="Service", language="java", file_path="A.java"),
            ArchElement(id="B", name="B", stereotype="Service", language="java", file_path="B.java"),
        ],
    )
    b = ArchSnapshot(
        snapshot_id="b",
        commit_sha="2",
        repo_path="/tmp",
        elements=[
            ArchElement(id="A", name="A", stereotype="Controller", language="java", file_path="A.java"),
            ArchElement(id="C", name="C", stereotype="Service", language="java", file_path="C.java"),
        ],
    )
    diff = DiffEngine().compare(a, b)
    assert {e.name for e in diff.added_elements} == {"C"}
    assert {e.name for e in diff.removed_elements} == {"B"}
    assert len(diff.modified_elements) == 1
    assert diff.has_changes
