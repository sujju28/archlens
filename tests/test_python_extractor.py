from pathlib import Path

from archlens.extractors.python_extractor import PythonExtractor

FIXTURES = Path(__file__).parent / "fixtures" / "python_fastapi"


def test_python_fastapi_routes_and_conventions():
    extractor = PythonExtractor(repo_root=FIXTURES)
    elements = []
    for path in FIXTURES.rglob("*.py"):
        if path.name == "__init__.py":
            continue
        elements.extend(extractor.extract_elements(path))

    by_name = {e.name: e for e in elements}
    assert "list_users" in by_name
    assert by_name["list_users"].stereotype == "Controller"
    assert "UserService" in by_name
    assert by_name["UserService"].stereotype == "Service"
    assert "UserRepository" in by_name
    assert by_name["UserRepository"].stereotype == "Repository"
