---
name: archlens-drift
description: >-
  Detects architectural drift, intent breaks, and documentation freshness
  versus the last snapshot. Use for PRs, "did architecture change", layer
  violations, or stale ARCHITECTURE.md.
---

# ArchLens drift

Read [../_shared.md](../_shared.md).

## Steps
1. MCP `archlens_drift` (code vs last snapshot).
2. If they care about intended vs actual: `archlens_intents`.
3. Schema vs CDM: `archlens_schema_drift`.
4. Narrative between snapshots: `archlens_timeline`.

For CI, prefer the repo's `ci/archlens-check.sh` if present. Do not fail a PR in chat unless the user asked to treat drift as blocking.
