# Shared ArchLens agent rules

Prefer **MCP tools** (`archlens_*`). If MCP is unavailable, use the `archlens` CLI with the same names (`archlens scan`, `playbook`, `explain`, …).

## Freshness
If `.archlens/` is missing, run `archlens init` then `archlens_scan`.
If there is no snapshot, or the user is on a different commit than the last scan, scan first.

## Honesty
- Cite tool output (element names, files, playbook steps). Do not invent owners, business rules, runtime behavior, or edges that are not in the snapshot.
- Candidate rules and test lists are heuristics. Say so.
- If the graph has no path, say it is not in the snapshot.

## Change work
Onboard → playbook → explain → impact → listed tests. Do not skip blast radius.
