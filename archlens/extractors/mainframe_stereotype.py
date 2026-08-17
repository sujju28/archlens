"""Behavioral stereotype inference for COBOL / mainframe programs."""

from __future__ import annotations

from typing import Any


def infer_mainframe_stereotype(
    analysis: dict[str, Any],
    *,
    override: str | None = None,
) -> str:
    """Infer stereotype from behavioral patterns (Phase 1.5).

    Priority matches the ArchLens mainframe implementation plan.
    """
    if override:
        return override

    if analysis.get("is_copybook"):
        return "Shared Data"
    if analysis.get("has_bms_send_map") or analysis.get("has_bms_receive_map"):
        return "UI Component"
    if analysis.get("has_mq_operations"):
        return "Gateway"
    if (analysis.get("has_exec_sql") or analysis.get("has_vsam_read_write")) and not (
        analysis.get("has_bms_send_map") or analysis.get("has_bms_receive_map")
    ):
        return "Repository"
    if analysis.get("called_via_cics_link") and not (
        analysis.get("has_bms_send_map") or analysis.get("has_bms_receive_map")
    ):
        return "Service"
    if analysis.get("called_via_jcl_exec_pgm"):
        return "Batch Job"
    if analysis.get("is_jcl_job"):
        return "Batch Job"
    return "Component"
