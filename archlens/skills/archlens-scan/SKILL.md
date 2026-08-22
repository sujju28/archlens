---
name: archlens-scan
description: >-
  Initializes ArchLens and refreshes the architecture snapshot. Use when the
  user asks to scan, map, or analyze architecture, when .archlens is missing,
  or before playbook, impact, explain, CDM, or onboard work if the snapshot
  may be stale.
---

# ArchLens scan

Read [../_shared.md](../_shared.md) for citation and freshness rules.

## Steps
1. If `.archlens/` is missing: `archlens init` (target repo root).
2. MCP `archlens_scan` with `repo_path` (or `archlens scan --repo <root>`).
3. Confirm `total_elements` / snapshot id in the tool result. Do not claim a scan succeeded without that.

Do not dump the full element list. Point to `archlens onboard` or `archlens capabilities` for orientation.
