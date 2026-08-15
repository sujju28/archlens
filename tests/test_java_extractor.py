from pathlib import Path

from archlens.extractors.java_extractor import JavaExtractor

FIXTURES = Path(__file__).parent / "fixtures" / "java_spring"


def test_java_extracts_spring_stereotypes():
    extractor = JavaExtractor(repo_root=FIXTURES)
    elements = []
    for path in FIXTURES.glob("*.java"):
        elements.extend(extractor.extract_elements(path))

    by_name = {e.name: e for e in elements}
    assert "UserController" in by_name
    assert by_name["UserController"].stereotype == "Controller"
    assert "UserService" in by_name
    assert by_name["UserService"].stereotype == "Service"
    assert "UserRepository" in by_name
    assert by_name["UserRepository"].stereotype == "Repository"
    assert "RestController" in by_name["UserController"].annotations


def test_java_relationships_injection():
    extractor = JavaExtractor(repo_root=FIXTURES)
    elements = []
    for path in FIXTURES.glob("*.java"):
        elements.extend(extractor.extract_elements(path))
    by_id = {e.id: e for e in elements}
    rels = []
    for path in FIXTURES.glob("*.java"):
        rels.extend(extractor.extract_relationships(path, by_id))

    injects = [r for r in rels if r.rel_type == "injects"]
    assert any("UserService" in r.target_id or "UserService" in r.description for r in injects)
