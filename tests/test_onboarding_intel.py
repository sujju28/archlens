"""Onboarding intel: explain, rules, grain, strangler, ops, reading priority."""

from pathlib import Path

from archlens.analysis.capabilities import Capability, CapabilityCatalog
from archlens.analysis.explain import explain_capability
from archlens.analysis.fine_grain import fine_grain_for
from archlens.analysis.onboard import onboard_markdown
from archlens.analysis.ops_overlay import ops_overlay
from archlens.analysis.playbook import build_playbook
from archlens.analysis.reading_priority import reading_priority
from archlens.analysis.source_harvest import harvest_for_elements
from archlens.analysis.strangler import strangler_slice
from archlens.extractors.bms_extractor import BmsExtractor
from archlens.extractors.cobol_extractor import CobolExtractor
from archlens.models import ArchElement, ArchRelationship, ArchSnapshot, C4Level

FIXTURES = Path(__file__).parent / "fixtures" / "cobol_cics"


def test_cobol_paragraphs_and_performs():
    extractor = CobolExtractor(repo_root=FIXTURES)
    els = extractor.extract_elements(FIXTURES / "CUSTINQ.cbl")
    prog = next(e for e in els if e.name == "CUSTINQ")
    paras = [e for e in els if (e.metadata or {}).get("kind") == "paragraph"]
    names = {e.name for e in paras}
    assert "1000-RECEIVE" in names
    assert prog.c4_level != C4Level.CODE.value
    assert all(p.c4_level == C4Level.CODE.value for p in paras)
    by_id = {e.id: e for e in els}
    rels = extractor.extract_relationships(FIXTURES / "CUSTINQ.cbl", by_id)
    assert any(r.rel_type == "performs" for r in rels)
    assert any(r.rel_type == "composes" and "para" in r.target_id for r in rels)
    assert any("inquiry" in (r.lower()) for r in (prog.metadata or {}).get("remarks", []))


def test_bms_fields():
    extractor = BmsExtractor(repo_root=FIXTURES)
    els = extractor.extract_elements(FIXTURES / "CUSTMAP.bms")
    assert any(e.name == "CUSTMAP" and e.metadata.get("kind") == "bms_map" for e in els)
    assert any(e.name == "CUSTNO" and e.metadata.get("kind") == "bms_field" for e in els)


def test_explain_and_rules_from_java(tmp_path: Path):
    src = tmp_path / "UserController.java"
    src.write_text(
        "package demo;\n"
        "/** Handles user account updates. */\n"
        "public class UserController {\n"
        "  public void save(User u) {\n"
        "    if (u.getStatus() != null) { }\n"
        "  }\n"
        "}\n",
        encoding="utf-8",
    )
    snap = ArchSnapshot(
        snapshot_id="s",
        commit_sha="a",
        repo_path=str(tmp_path),
        elements=[
            ArchElement(
                id="C",
                name="UserController",
                stereotype="Controller",
                language="java",
                file_path="UserController.java",
                metadata={"methods": ["save"]},
            ),
            ArchElement(
                id="U",
                name="User",
                stereotype="Entity",
                language="java",
                file_path="User.java",
            ),
        ],
        relationships=[
            ArchRelationship(source_id="C", target_id="U", rel_type="injects"),
        ],
        metadata={"project_name": "Demo"},
    )
    cap = Capability(
        id="usercontroller",
        title="Manage users",
        stereotype="Controller",
        elements=["UserController"],
        related_tables=["users"],
    )
    expl = explain_capability(snap, cap, repo=tmp_path, use_llm=False)
    assert expl.llm_used is False
    assert "UserController" in expl.narrative
    assert any("Handles user" in c["text"] or "javadoc" in c["text"] for c in expl.citations)
    h = harvest_for_elements(snap, [snap.elements[0]], tmp_path)
    assert h.comments
    assert any(r.kind == "if" for r in h.rules)
    pb = build_playbook(snap, cap, repo=tmp_path)
    assert pb.comments
    md = pb.to_markdown()
    assert "Candidate business rules" in md or pb.rules
    slice_ = strangler_slice(
        snap,
        capability_id=cap.id,
        title=cap.title,
        seed_names=cap.elements,
        related_tables=cap.related_tables,
    )
    assert "UserController" in slice_.programs
    assert "users" in slice_.tables or "User" in slice_.tables
    grain = fine_grain_for(snap, [snap.elements[0]], repo=tmp_path)
    assert "save" in grain.methods
    catalog = CapabilityCatalog(capabilities=[cap])
    onboard = onboard_markdown(snap, catalog, repo=tmp_path)
    assert "90 minutes" in onboard
    assert "Manage users" in onboard


def test_reading_priority_and_ops():
    snap = ArchSnapshot(
        snapshot_id="s",
        commit_sha="a",
        repo_path="/tmp",
        elements=[
            ArchElement(id="C", name="Api", stereotype="Controller", language="java", file_path="A.java"),
            ArchElement(id="S", name="Svc", stereotype="Service", language="java", file_path="S.java"),
            ArchElement(
                id="D",
                name="DeadUtil",
                stereotype="Component",
                language="java",
                file_path="D.java",
            ),
            ArchElement(
                id="J",
                name="NIGHTLY",
                stereotype="Batch Job",
                language="jcl",
                file_path="N.jcl",
                metadata={"kind": "jcl_job"},
            ),
        ],
        relationships=[
            ArchRelationship(source_id="C", target_id="S", rel_type="injects"),
        ],
    )
    prio = reading_priority(snap, seed_names=["Api"])
    assert any("Api" in x or "Entry" in x for x in prio.learn_first)
    assert any("DeadUtil" in x for x in prio.skip_or_later)
    ops = ops_overlay(snap, seed_names=["Api"])
    assert "NIGHTLY" in ops.jobs
