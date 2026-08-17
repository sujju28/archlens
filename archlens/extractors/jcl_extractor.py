"""JCL (Job Control Language) extractor — regex-based."""

from __future__ import annotations

import re
from pathlib import Path

from archlens.extractors.base import BaseExtractor
from archlens.models import ArchElement, ArchRelationship, RelType

_JOB = re.compile(r"^//(\w+)\s+JOB\b", re.IGNORECASE | re.MULTILINE)
_EXEC_PGM = re.compile(
    r"^//(\w+)\s+EXEC\s+(?:PGM=([A-Z0-9$#@]+)|PROC=([A-Z0-9$#@]+))",
    re.IGNORECASE | re.MULTILINE,
)
_DD_DSN = re.compile(
    r"^//(\w+)\s+DD\b.*?DSN=([A-Z0-9.#@$-]+)(.*)$",
    re.IGNORECASE | re.MULTILINE,
)
_DISP = re.compile(r"DISP\s*=\s*\(?\s*([^)\s,]+)", re.IGNORECASE)


class JclExtractor(BaseExtractor):
    language = "jcl"

    def supported_extensions(self) -> set[str]:
        return {".jcl", ".proc"}

    def extract_elements(self, file_path: Path) -> list[ArchElement]:
        text = file_path.read_text(encoding="utf-8", errors="replace")
        rel = self.relative_path(file_path)
        elements: list[ArchElement] = []

        job_name = None
        jm = _JOB.search(text)
        if jm:
            job_name = jm.group(1).upper()
        else:
            job_name = file_path.stem.upper()

        job_id = f"jcl.{job_name}"
        elements.append(
            ArchElement(
                id=job_id,
                name=job_name,
                stereotype="Batch Job",
                language="jcl",
                file_path=rel,
                metadata={"kind": "jcl_job", "is_jcl_job": True},
            )
        )

        steps: list[dict] = []
        for m in _EXEC_PGM.finditer(text):
            step = m.group(1).upper()
            pgm = (m.group(2) or "").upper() or None
            proc = (m.group(3) or "").upper() or None
            steps.append({"step": step, "pgm": pgm, "proc": proc})
            step_id = f"jcl.{job_name}.{step}"
            target = pgm or proc or step
            elements.append(
                ArchElement(
                    id=step_id,
                    name=f"{job_name}.{step}",
                    stereotype="Batch Job",
                    language="jcl",
                    file_path=rel,
                    metadata={
                        "kind": "jcl_step",
                        "job": job_name,
                        "step": step,
                        "pgm": pgm,
                        "proc": proc,
                        "exec_target": target,
                    },
                )
            )
            # Placeholder COBOL program so relationships can resolve after scan
            if pgm:
                elements.append(
                    ArchElement(
                        id=f"cobol.{pgm}",
                        name=pgm,
                        stereotype="Batch Job",
                        language="cobol",
                        file_path=rel,
                        metadata={
                            "kind": "program_ref",
                            "from_jcl": True,
                            "called_via_jcl_exec_pgm": True,
                        },
                    )
                )

        # Datasets
        for m in _DD_DSN.finditer(text):
            dd = m.group(1).upper()
            dsn = m.group(2).upper()
            rest = m.group(3) or ""
            disp_m = _DISP.search(rest) or _DISP.search(m.group(0))
            disp = (disp_m.group(1).upper() if disp_m else "SHR")
            ds_id = f"dataset.{dsn}"
            elements.append(
                ArchElement(
                    id=ds_id,
                    name=dsn,
                    stereotype="Shared Data",
                    language="dataset",
                    file_path=rel,
                    metadata={"kind": "dataset", "dd": dd, "disp": disp},
                )
            )

        # Attach step list on job
        for el in elements:
            if el.id == job_id:
                el.metadata["steps"] = steps

        return elements

    def extract_relationships(
        self, file_path: Path, elements: dict[str, ArchElement]
    ) -> list[ArchRelationship]:
        text = file_path.read_text(encoding="utf-8", errors="replace")
        rel = self.relative_path(file_path)
        jobs = [
            e
            for e in elements.values()
            if e.file_path == rel and e.metadata.get("kind") == "jcl_job"
        ]
        if not jobs:
            return []
        job = jobs[0]
        rels: list[ArchRelationship] = []

        for e in elements.values():
            if e.file_path != rel:
                continue
            if e.metadata.get("kind") == "jcl_step":
                rels.append(
                    ArchRelationship(
                        source_id=job.id,
                        target_id=e.id,
                        rel_type=RelType.COMPOSES.value,
                        description=f"job step {e.metadata.get('step')}",
                        technology="JCL",
                    )
                )
                pgm = e.metadata.get("pgm")
                proc = e.metadata.get("proc")
                if pgm:
                    rels.append(
                        ArchRelationship(
                            source_id=e.id,
                            target_id=f"cobol.{pgm}",
                            rel_type=RelType.EXECUTES.value,
                            description=f"EXEC PGM={pgm}",
                            technology="JCL",
                        )
                    )
                if proc:
                    rels.append(
                        ArchRelationship(
                            source_id=e.id,
                            target_id=f"jcl.{proc}",
                            rel_type=RelType.CALLS.value,
                            description=f"EXEC PROC={proc}",
                            technology="JCL",
                        )
                    )

        # DD DSN relationships: attach to nearest preceding step (simplified: job)
        for m in _DD_DSN.finditer(text):
            dsn = m.group(2).upper()
            rest = m.group(3) or ""
            disp_m = _DISP.search(rest) or _DISP.search(m.group(0))
            disp = (disp_m.group(1).upper() if disp_m else "SHR")
            # NEW / MOD → write; SHR / OLD → read
            is_write = disp in ("NEW", "MOD") or "NEW" in disp
            rel_type = RelType.WRITES_DATASET.value if is_write else RelType.READS_DATASET.value
            # Prefer last step before this DD if we can; else job
            src = job.id
            for e in elements.values():
                if (
                    e.file_path == rel
                    and e.metadata.get("kind") == "jcl_step"
                    and e.metadata.get("pgm")
                ):
                    src = e.id  # last step wins (simple heuristic)
            rels.append(
                ArchRelationship(
                    source_id=src,
                    target_id=f"dataset.{dsn}",
                    rel_type=rel_type,
                    description=f"DD DSN={dsn} DISP={disp}",
                    technology="JCL",
                )
            )

        return rels
