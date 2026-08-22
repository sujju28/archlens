"""Tests for aggregate CDM + semantic overlays + basic data-model report."""

from pathlib import Path

from archlens.analysis.cdm_semantics import CdmSemantics, SameAsGroup
from archlens.analysis.data_model import (
    basic_data_model_markdown,
    build_canonical_data_model,
    build_cdm_from_exports,
)
from archlens.distributed.aggregator import aggregate_snapshots
from archlens.models import ArchElement, ArchSnapshot


def _entity(eid: str, name: str, table: str, cols: list[str], fks: list[str] | None = None):
    return ArchElement(
        id=eid,
        name=name,
        stereotype="Entity",
        language="java",
        file_path=f"{name}.java",
        metadata={
            "table_name": table,
            "columns": cols,
            "fk_columns": fks or [],
            "kind": "jpa",
        },
    )


def test_semantics_alias_owner_suppress():
    snap = ArchSnapshot(
        snapshot_id="s1",
        commit_sha="a",
        repo_path="/tmp/a",
        elements=[
            _entity("U", "User", "users", ["id", "email"]),
            _entity("N", "Noise", "SYSDUMMY1", ["x"]),
        ],
    )
    sem = CdmSemantics(
        aliases={"users": "Customer"},
        owners={"Customer": "team-crm"},
        suppress=["SYSDUMMY1"],
    )
    cdm = build_canonical_data_model(snap, semantics=sem)
    names = {e.table_name for e in cdm.entities}
    assert "Customer" in names
    assert "SYSDUMMY1" not in names
    cust = next(e for e in cdm.entities if e.table_name == "Customer")
    assert cust.owner == "team-crm"
    assert "users" in cust.aliases or cust.canonical_name == "Customer"


def test_same_as_merges_tables_and_columns():
    snap = ArchSnapshot(
        snapshot_id="s1",
        commit_sha="a",
        repo_path="/tmp/a",
        elements=[
            _entity("A", "UserModel", "users", ["id", "email"]),
            _entity("B", "CustomerPO", "C_BPartner", ["C_BPartner_ID", "Name"], ["AD_Client_ID"]),
        ],
    )
    sem = CdmSemantics(
        same_as=[
            SameAsGroup(
                canonical="Customer",
                tables=["users", "C_BPartner"],
                description="party",
            )
        ],
        owners={"Customer": "crm"},
    )
    cdm = build_canonical_data_model(snap, semantics=sem)
    assert cdm.stats["entity_count"] == 1
    cust = cdm.entities[0]
    assert cust.table_name == "Customer"
    assert "email" in cust.columns
    assert "Name" in cust.columns or "C_BPartner_ID" in cust.columns
    assert cust.owner == "crm"


def test_aggregate_cdm_merges_cross_repo(tmp_path: Path):
    billing = ArchSnapshot(
        snapshot_id="b",
        commit_sha="1",
        repo_path="/tmp/billing",
        elements=[_entity("U", "User", "users", ["id", "email"])],
        metadata={"project_name": "billing"},
    )
    orders = ArchSnapshot(
        snapshot_id="o",
        commit_sha="2",
        repo_path="/tmp/orders",
        elements=[
            _entity(
                "C",
                "Customer",
                "customers",
                ["id", "name"],
                ["user_id"],
            )
        ],
        metadata={"project_name": "orders"},
    )
    p1 = tmp_path / "billing.json"
    p2 = tmp_path / "orders.json"
    p1.write_text(billing.model_dump_json(), encoding="utf-8")
    p2.write_text(orders.model_dump_json(), encoding="utf-8")

    sem = CdmSemantics(
        same_as=[SameAsGroup(canonical="Customer", tables=["users", "customers"])],
        owners={"Customer": "platform"},
    )
    snap, cdm = build_cdm_from_exports(
        [p1, p2], system_name="Shop", semantics=sem
    )
    assert snap.metadata["aggregated"] is True
    assert cdm.stats["aggregated"] is True
    assert cdm.stats["entity_count"] == 1
    cust = cdm.entities[0]
    assert cust.table_name == "Customer"
    assert len(cust.source_repos) >= 1
    assert "email" in cust.columns and ("name" in cust.columns or "id" in cust.columns)


def test_basic_data_model_standalone_markdown():
    snap = ArchSnapshot(
        snapshot_id="s1",
        commit_sha="a",
        repo_path="/tmp/a",
        elements=[_entity("U", "User", "users", ["id"])],
        metadata={"project_name": "Demo"},
    )
    md = basic_data_model_markdown(snap)
    assert "Basic data model" in md
    assert "users" in md


def test_aggregate_preserves_source_slug_for_cdm():
    a = ArchSnapshot(
        snapshot_id="a",
        commit_sha="1",
        repo_path="/tmp/billing",
        elements=[_entity("U", "User", "users", ["id"])],
        metadata={"project_name": "billing"},
    )
    b = ArchSnapshot(
        snapshot_id="b",
        commit_sha="2",
        repo_path="/tmp/orders",
        elements=[_entity("O", "Order", "orders", ["id", "users_id"], ["users_id"])],
        metadata={"project_name": "orders"},
    )
    agg = aggregate_snapshots([a, b], system_name="Shop")
    sem = CdmSemantics(aliases={"users": "Customer", "user": "Customer"})
    cdm = build_canonical_data_model(agg, semantics=sem)
    tables = {e.table_name for e in cdm.entities}
    assert "Customer" in tables
    assert "orders" in tables
    # FK users_id → users → Customer via alias
    assert any(a.target_table == "Customer" for a in cdm.associations)
