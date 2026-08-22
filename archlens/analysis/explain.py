"""Grounded explain: prose from cited snippets (+ optional LLM, never unsourced)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from archlens.analysis.capabilities import Capability
from archlens.analysis.fine_grain import fine_grain_for
from archlens.analysis.ops_overlay import ops_overlay
from archlens.analysis.playbook import ChangePlaybook, build_playbook
from archlens.analysis.reading_priority import reading_priority
from archlens.analysis.source_harvest import harvest_for_elements
from archlens.analysis.strangler import strangler_slice
from archlens.models import ArchSnapshot


@dataclass
class GroundedExplain:
    capability_id: str
    title: str
    narrative: str
    citations: list[dict[str, str]] = field(default_factory=list)
    llm_used: bool = False
    playbook_markdown: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "title": self.title,
            "narrative": self.narrative,
            "citations": self.citations,
            "llm_used": self.llm_used,
        }

    def to_markdown(self) -> str:
        src = "LLM (citations only)" if self.llm_used else "graph + file citations (no LLM)"
        lines = [
            f"# Explain: {self.title}",
            "",
            f"_Grounded in ArchLens citations — {src}. Not a BA spec._",
            "",
            self.narrative.strip(),
            "",
            "## Citations",
            "",
        ]
        for c in self.citations[:20]:
            lines.append(f"- `{c.get('ref', '')}` — {c.get('text', '')[:200]}")
        lines.append("")
        if self.playbook_markdown:
            lines.append("---")
            lines.append("")
            lines.append(self.playbook_markdown)
        return "\n".join(lines)


def explain_capability(
    snapshot: ArchSnapshot,
    capability: Capability,
    *,
    repo: Path | str | None = None,
    use_llm: bool = True,
) -> GroundedExplain:
    root = Path(repo or snapshot.repo_path)
    pb = build_playbook(snapshot, capability, repo=root)
    by_name = {e.name: e for e in snapshot.elements}
    seeds = [by_name[n] for n in capability.elements if n in by_name]
    harvest = harvest_for_elements(snapshot, seeds, root)
    citations: list[dict[str, str]] = []
    for step in pb.reading_path:
        if step.excerpt:
            citations.append({"ref": step.citation or step.file_path, "text": step.excerpt})
    for c in harvest.comments:
        citations.append({"ref": c.citation, "text": f"[{c.kind}] {c.text}"})
    for r in harvest.rules[:8]:
        citations.append({"ref": r.citation, "text": f"rule {r.kind}: {r.text}"})

    template = _template_narrative(capability, pb, harvest, citations)
    llm_text = _llm_from_citations(capability.title, citations) if use_llm else None
    narrative = llm_text or template
    return GroundedExplain(
        capability_id=capability.id,
        title=capability.title or capability.id,
        narrative=narrative,
        citations=citations,
        llm_used=bool(llm_text),
        playbook_markdown=pb.to_markdown(),
    )


def enrich_playbook_extras(
    snapshot: ArchSnapshot,
    capability: Capability,
    pb: ChangePlaybook,
    *,
    repo: Path | str | None = None,
) -> ChangePlaybook:
    """Attach harvest / slice / ops / reading order onto an existing playbook."""
    root = Path(repo or snapshot.repo_path)
    by_name = {e.name: e for e in snapshot.elements}
    seeds = [by_name[n] for n in capability.elements if n in by_name]
    harvest = harvest_for_elements(snapshot, seeds, root)
    grain = fine_grain_for(snapshot, seeds, repo=root, capability_id=capability.id)
    slice_ = strangler_slice(
        snapshot,
        capability_id=capability.id,
        title=capability.title or capability.id,
        seed_names=list(capability.elements),
        related_tables=list(capability.related_tables),
    )
    ops = ops_overlay(snapshot, repo=root, seed_names=list(capability.elements))
    prio = reading_priority(snapshot, seed_names=list(capability.elements))
    pb.comments = [f"`{c.citation}` — {c.text}" for c in harvest.comments]
    pb.rules = [f"{r.kind}: {r.text} (`{r.citation}`)" for r in harvest.rules]
    pb.methods = harvest.methods or grain.methods
    pb.paragraphs = harvest.paragraphs or [p["name"] for p in grain.paragraphs]
    pb.bms_fields = harvest.bms_fields or grain.bms_fields
    pb.strangler = (
        [f"programs: {', '.join(slice_.programs[:8])}"] if slice_.programs else []
    )
    if slice_.tables:
        pb.strangler.append("tables: " + ", ".join(slice_.tables[:8]))
    if slice_.jobs:
        pb.strangler.append("jobs: " + ", ".join(slice_.jobs[:6]))
    pb.ops = (
        [f"jobs: {', '.join(ops.jobs)}"] if ops.jobs else []
    )
    if ops.transids:
        pb.ops.append("TRANSID: " + ", ".join(ops.transids[:8]))
    if ops.maps:
        pb.ops.append("maps: " + ", ".join(ops.maps[:8]))
    pb.learn_first = prio.learn_first
    pb.skip_or_later = prio.skip_or_later[:8]
    if grain.copy_usage and not pb.copybooks:
        pb.copybooks = harvest.copybooks
    return pb


def _template_narrative(
    capability: Capability,
    pb: ChangePlaybook,
    harvest,
    citations: list[dict[str, str]],
) -> str:
    start = pb.reading_path[0].name if pb.reading_path else (capability.elements[0] if capability.elements else capability.id)
    bits = [
        f"**{capability.title or capability.id}** is entered through `{start}`"
        f" ({pb.stereotype or capability.stereotype or 'entry'})."
    ]
    if len(pb.reading_path) > 1:
        chain = " → ".join(f"`{s.name}`" for s in pb.reading_path[:6])
        bits.append(f"Linked reading order: {chain}.")
    if harvest.comments:
        bits.append("Source remarks/docs: " + harvest.comments[0].text[:180])
    if harvest.rules:
        bits.append(
            "Candidate rules in code (names for humans): "
            + "; ".join(f"{r.kind} {r.text[:60]}" for r in harvest.rules[:4])
            + "."
        )
    if pb.tables:
        bits.append("Data: " + ", ".join(f"`{t}`" for t in pb.tables[:8]) + ".")
    if not citations:
        bits.append("No file excerpts were available; re-scan and keep sources on disk.")
    bits.append("Change only after the playbook blast radius and tests below.")
    return " ".join(bits)


def _llm_from_citations(title: str, citations: list[dict[str, str]]) -> str | None:
    key = os.environ.get("ARCHLENS_LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not key or not citations:
        return None
    url = os.environ.get("ARCHLENS_LLM_URL", "https://api.openai.com/v1/chat/completions")
    model = os.environ.get("ARCHLENS_LLM_MODEL", "gpt-4o-mini")
    blob = "\n".join(f"- {c['ref']}: {c['text']}" for c in citations[:16])
    payload = {
        "model": model,
        "temperature": 0.2,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Explain a software capability for a new developer. "
                    "Use ONLY the provided citations. If something is not cited, say you do not know. "
                    "Do not invent business rules, owners, or runtime behavior."
                ),
            },
            {
                "role": "user",
                "content": f"Capability: {title}\nCitations:\n{blob}",
            },
        ],
    }
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=25) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        text = data["choices"][0]["message"]["content"]
        return str(text).strip() or None
    except (urllib.error.URLError, KeyError, IndexError, TimeoutError, json.JSONDecodeError, OSError):
        return None
