from archlens.analysis.impact_analyzer import ImpactAnalyzer
from archlens.models import ArchElement, ArchRelationship, ArchSnapshot


def _sample_snapshot() -> ArchSnapshot:
    elements = [
        ArchElement(id="UserController", name="UserController", stereotype="Controller", language="java", file_path="UserController.java"),
        ArchElement(id="UserService", name="UserService", stereotype="Service", language="java", file_path="UserService.java"),
        ArchElement(id="OrderService", name="OrderService", stereotype="Service", language="java", file_path="OrderService.java"),
        ArchElement(id="UserRepository", name="UserRepository", stereotype="Repository", language="java", file_path="UserRepository.java"),
    ]
    relationships = [
        ArchRelationship(source_id="UserController", target_id="UserService", rel_type="injects"),
        ArchRelationship(source_id="OrderService", target_id="UserService", rel_type="calls"),
        ArchRelationship(source_id="UserService", target_id="UserRepository", rel_type="injects"),
    ]
    return ArchSnapshot(
        snapshot_id="s1",
        commit_sha="abc",
        repo_path="/tmp",
        elements=elements,
        relationships=relationships,
    )


def test_impact_upstream_from_service():
    report = ImpactAnalyzer().analyze(_sample_snapshot(), elements=["UserService"], depth=3)
    names = {a.name for a in report.directly_affected}
    assert "UserController" in names
    assert "OrderService" in names
    assert report.risk_score > 0
    assert report.suggested_changes
