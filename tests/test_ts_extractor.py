from pathlib import Path

from archlens.extractors.ts_extractor import TypeScriptExtractor

NESTJS = Path(__file__).parent / "fixtures" / "typescript_nestjs"
REACT = Path(__file__).parent / "fixtures" / "typescript_react"


def test_nestjs_decorators():
    extractor = TypeScriptExtractor(repo_root=NESTJS)
    elements = []
    for path in NESTJS.glob("*.ts"):
        elements.extend(extractor.extract_elements(path))
    by_name = {e.name: e for e in elements}
    assert by_name["UserController"].stereotype == "Controller"
    assert by_name["UserService"].stereotype == "Service"
    assert "Controller" in by_name["UserController"].annotations
    assert "Injectable" in by_name["UserService"].annotations


def test_react_functional_components():
    extractor = TypeScriptExtractor(repo_root=REACT)
    elements = []
    for path in REACT.glob("*.tsx"):
        elements.extend(extractor.extract_elements(path))
    by_name = {e.name: e for e in elements}
    assert "UserList" in by_name
    assert by_name["UserList"].stereotype == "UI Component"
    assert "UserCard" in by_name
    assert by_name["UserCard"].stereotype == "UI Component"
