# ArchLens Conventions

Use ArchLens when the user asks about architecture, dependencies, impact of changes,
diagrams, or documentation freshness.

Workflow:
1. Ensure a fresh scan (`archlens scan` or MCP `archlens_scan`)
2. Prefer MCP tools when available; otherwise call the CLI / helper scripts
3. Always explain WHY components are affected (dependency chains)
4. Be conservative with effort estimates
