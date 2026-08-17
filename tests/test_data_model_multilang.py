from pathlib import Path

from archlens.analysis.data_model import (
    basic_data_model_summary,
    build_canonical_data_model,
)
from archlens.config import ArchLensConfig
from archlens.extractors.cobol_extractor import CobolExtractor
from archlens.extractors.entity_metadata import parse_entity_metadata
from archlens.extractors.python_extractor import PythonExtractor
from archlens.extractors.ts_extractor import TypeScriptExtractor
from archlens.generators.markdown_report import MarkdownReportGenerator
from archlens.scanner import scan_repository

TS_FIX = Path(__file__).parent / "fixtures" / "typescript_nestjs"
PY_FIX = Path(__file__).parent / "fixtures" / "python_fastapi"
COBOL_FIX = Path(__file__).parent / "fixtures" / "cobol_cics"


def test_typescript_entity_metadata():
    extractor = TypeScriptExtractor(repo_root=TS_FIX)
    els = extractor.extract_elements(TS_FIX / "user.entity.ts")
    user = next(e for e in els if e.name == "User")
    assert user.stereotype == "Entity"
    assert user.metadata.get("table_name") == "users"
    cols = user.metadata.get("columns", [])
    assert "email" in cols
    assert "id" in cols
    fks = user.metadata.get("fk_columns", [])
    assert "order_id" in fks or "orderId" in fks


def test_python_sqlalchemy_and_dataclass_metadata():
    extractor = PythonExtractor(repo_root=PY_FIX)
    els = extractor.extract_elements(PY_FIX / "models" / "user_models.py")
    by_name = {e.name: e for e in els}
    assert by_name["UserModel"].stereotype == "Entity"
    assert by_name["UserModel"].metadata.get("table_name") == "users"
    assert "email" in by_name["UserModel"].metadata.get("columns", [])
    assert by_name["OrderRecord"].stereotype == "Entity"
    assert "status" in by_name["OrderRecord"].metadata.get("columns", [])


def test_cobol_dclgen_enriches_db2_entity():
    extractor = CobolExtractor(repo_root=COBOL_FIX)
    els = extractor.extract_elements(COBOL_FIX / "DCLCUST.cpy")
    cust = next(
        (
            e
            for e in els
            if e.stereotype == "Entity"
            and (e.name == "CUSTOMER" or e.metadata.get("table_name") == "CUSTOMER")
        ),
        None,
    )
    assert cust is not None
    cols = cust.metadata.get("columns") or []
    assert "CUSTNO" in cols
    assert "WAREHOUSE_ID" in cols
    assert "WAREHOUSE_ID" in (cust.metadata.get("fk_columns") or [])


def test_parse_helpers_language_dispatch():
    java = parse_entity_metadata(
        "I_C_Order",
        'String Table_Name = "C_Order";\nString COLUMNNAME_C_BPartner_ID = "C_BPartner_ID";',
        language="java",
    )
    assert java["table_name"] == "C_Order"
    assert "C_BPartner_ID" in java["fk_columns"]


def test_cross_stack_cdm_and_basic_summary():
    cfg = ArchLensConfig(
        project_name="Multi",
        languages=["typescript", "python", "cobol"],
        include=[""],
        exclude=[".archlens/"],
    )
    snap = scan_repository(TS_FIX, config=cfg, persist=False)
    cdm = build_canonical_data_model(snap)
    assert cdm.stats["entity_count"] >= 2
    assert cdm.stats.get("languages")
    basic = basic_data_model_summary(snap)
    assert basic["entity_count"] >= 2
    assert basic.get("sample_tables")
    md = MarkdownReportGenerator().generate(snap)
    assert "## Basic data model" in md
    assert "Sample tables" in md or "sample tables" in md.lower() or "Sample tables" in md
