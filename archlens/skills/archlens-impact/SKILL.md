---
name: archlens-impact
description: >-
  Analyzes blast radius of file or component changes and PR risk. Use when
  the user asks what breaks if they change X, impact of a PR, effort, or
  who depends on a program/class.
---

# ArchLens impact

Read [../_shared.md](../_shared.md). Scan first if stale.

## Steps
1. MCP `archlens_impact` with `repo_path` and `files` and/or `elements`.
2. Report risk score, direct vs transitive, and suggested next actions from the tool.
3. Show **why** (relationship types), not only names.
4. If they are extracting or strangling a capability: MCP `archlens_strangler` with `capability`.

Do not estimate calendar time unless the tool's effort helpers are used; stay conservative.

CLI: `archlens impact --repo <root> --files <paths>`
