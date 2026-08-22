---
name: archlens-legacy
description: >-
  Navigates COBOL, CICS, BMS, JCL, and COPY using ArchLens fine grain and
  ops overlay. Use when the user mentions programs, paragraphs, PERFORM,
  TRANSID, maps, batch jobs, or mainframe change.
---

# ArchLens legacy (COBOL / CICS / JCL)

Read [../_shared.md](../_shared.md). Scan first if stale.

## Steps
1. Resolve capability or program via `archlens_capabilities` / `archlens_query`.
2. MCP `archlens_playbook` then `archlens_grain` (paragraphs, PERFORM, BMS fields, COPY).
3. MCP `archlens_ops` for job names and TRANSID.
4. MCP `archlens_rules` for candidate IF/EVALUATE (checklist, not a BRD).

Do not invent paragraph purpose beyond names and cited remarks. Maps/fields come from BMS/CICS edges only.
