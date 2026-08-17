from pathlib import Path

from archlens.config import ArchLensConfig, MainframeConfig, MainframeStereotypeOverride
from archlens.extractors.cobol_extractor import CobolExtractor, normalize_cobol_source
from archlens.extractors.jcl_extractor import JclExtractor
from archlens.extractors.mainframe_stereotype import infer_mainframe_stereotype
from archlens.scanner import scan_repository

FIXTURES = Path(__file__).parent / "fixtures" / "cobol_cics"


def test_normalize_strips_sequence_and_comments():
    raw = "000100* COMMENT LINE\n000200       PROGRAM-ID. FOO.\n"
    out = normalize_cobol_source(raw)
    assert "COMMENT" not in out
    assert "PROGRAM-ID" in out


def test_cobol_custinq_is_ui_and_links_service():
    extractor = CobolExtractor(repo_root=FIXTURES)
    els = extractor.extract_elements(FIXTURES / "CUSTINQ.cbl")
    prog = next(e for e in els if e.name == "CUSTINQ")
    assert prog.stereotype == "UI Component"
    by_id = {e.id: e for e in els}
    # add CUSTSVC so relationship resolves later
    svc = CobolExtractor(repo_root=FIXTURES).extract_elements(FIXTURES / "CUSTSVC.cbl")
    for e in svc:
        by_id[e.id] = e
    rels = extractor.extract_relationships(FIXTURES / "CUSTINQ.cbl", by_id)
    assert any(r.rel_type == "cics_link" and "CUSTSVC" in r.target_id for r in rels)
    assert any(r.rel_type == "uses_map" for r in rels)


def test_cobol_custsvc_is_repository_with_sql():
    extractor = CobolExtractor(repo_root=FIXTURES)
    els = extractor.extract_elements(FIXTURES / "CUSTSVC.cbl")
    prog = next(e for e in els if e.name == "CUSTSVC")
    assert prog.stereotype == "Repository"
    assert any(e.name == "CUSTOMER" and e.stereotype == "Entity" for e in els)
    by_id = {e.id: e for e in els}
    rels = extractor.extract_relationships(FIXTURES / "CUSTSVC.cbl", by_id)
    assert any(r.rel_type == "accesses_table" for r in rels)
    assert any(r.rel_type == "writes_table" for r in rels)


def test_copybook_is_shared_data():
    extractor = CobolExtractor(repo_root=FIXTURES)
    els = extractor.extract_elements(FIXTURES / "CUSTCPY.cpy")
    assert els[0].stereotype == "Shared Data"


def test_jcl_batch_flow():
    extractor = JclExtractor(repo_root=FIXTURES)
    els = extractor.extract_elements(FIXTURES / "NIGHTLY.jcl")
    by_name = {e.name: e for e in els}
    assert "NIGHTLY" in by_name
    assert by_name["NIGHTLY"].stereotype == "Batch Job"
    assert any(e.metadata.get("pgm") == "EXTRACT" for e in els)
    by_id = {e.id: e for e in els}
    rels = extractor.extract_relationships(FIXTURES / "NIGHTLY.jcl", by_id)
    assert any(r.rel_type == "executes" and "EXTRACT" in r.target_id for r in rels)
    assert any(r.rel_type == "reads_dataset" for r in rels)
    assert any(r.rel_type == "writes_dataset" for r in rels)


def test_stereotype_override_from_config():
    cfg = ArchLensConfig(
        mainframe=MainframeConfig(
            stereotypes=[
                MainframeStereotypeOverride(program="CUSTINQ", stereotype="Controller"),
            ]
        )
    )
    extractor = CobolExtractor(config=cfg, repo_root=FIXTURES)
    els = extractor.extract_elements(FIXTURES / "CUSTINQ.cbl")
    prog = next(e for e in els if e.name == "CUSTINQ")
    assert prog.stereotype == "Controller"


def test_infer_mainframe_stereotype_rules():
    assert infer_mainframe_stereotype({"is_copybook": True}) == "Shared Data"
    assert (
        infer_mainframe_stereotype({"has_bms_send_map": True, "has_bms_receive_map": True})
        == "UI Component"
    )
    assert infer_mainframe_stereotype({"has_mq_operations": True}) == "Gateway"
    assert infer_mainframe_stereotype({"has_exec_sql": True}) == "Repository"
    assert (
        infer_mainframe_stereotype({"called_via_cics_link": True}) == "Service"
    )
    assert (
        infer_mainframe_stereotype({"called_via_jcl_exec_pgm": True}) == "Batch Job"
    )


def test_scan_mainframe_fixture_end_to_end():
    cfg = ArchLensConfig(
        project_name="Mainframe Demo",
        languages=["cobol"],
        include=[""],
        exclude=[".archlens/"],
    )
    snap = scan_repository(FIXTURES, config=cfg, persist=False)
    names = {e.name for e in snap.elements}
    assert "CUSTINQ" in names
    assert "CUSTSVC" in names
    assert "NIGHTLY" in names
    assert "CUSTOMER" in names
    rel_types = {r.rel_type for r in snap.relationships}
    assert "cics_link" in rel_types
    assert "executes" in rel_types
