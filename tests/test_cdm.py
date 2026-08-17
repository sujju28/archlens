from pathlib import Path

from archlens.analysis.data_model import build_canonical_data_model, link_entity_foreign_keys
from archlens.extractors.java_extractor import JavaExtractor
from archlens.extractors.stereotype import resolve_stereotype
from archlens.generators.cdm_report import CdmReportGenerator
from archlens.models import ArchSnapshot

FIXTURES = Path(__file__).parent / "fixtures" / "java_po"


def test_po_naming_is_entity():
    assert (
        resolve_stereotype(
            language="java", name="I_C_Order", file_path="I_C_Order.java", annotations=[]
        )
        == "Entity"
    )
    assert (
        resolve_stereotype(
            language="java",
            name="X_C_BPartner",
            file_path="X_C_BPartner.java",
            annotations=[],
        )
        == "Entity"
    )


def test_java_extracts_po_interfaces_with_columns():
    extractor = JavaExtractor(repo_root=FIXTURES)
    elements = []
    for path in FIXTURES.glob("I_*.java"):
        elements.extend(extractor.extract_elements(path))
    by_name = {e.name: e for e in elements}
    assert "I_C_Order" in by_name
    order = by_name["I_C_Order"]
    assert order.stereotype == "Entity"
    assert order.metadata.get("table_name") == "C_Order"
    assert "C_BPartner_ID" in order.metadata.get("columns", [])
    assert "C_BPartner_ID" in order.metadata.get("fk_columns", [])


def test_fk_linking_and_cdm_report():
    extractor = JavaExtractor(repo_root=FIXTURES)
    elements = []
    for path in FIXTURES.glob("I_*.java"):
        elements.extend(extractor.extract_elements(path))
    rels = link_entity_foreign_keys(elements, [])
    refs = [r for r in rels if r.rel_type == "references"]
    assert any("C_BPartner" in (r.description or "") for r in refs)
    assert any("M_Warehouse" in (r.description or "") for r in refs)

    snap = ArchSnapshot(
        snapshot_id="s",
        commit_sha="x",
        repo_path=str(FIXTURES),
        metadata={"project_name": "PO Demo"},
        elements=elements,
        relationships=rels,
    )
    cdm = build_canonical_data_model(snap)
    assert cdm.stats["entity_count"] == 3
    assert cdm.stats["association_count"] >= 2
    md = CdmReportGenerator().generate(snap, cdm)
    assert "Canonical Data Model" in md
    assert "erDiagram" in md
    assert "C_Order" in md
