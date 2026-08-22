# ArchLens

Living architecture intelligence for any codebase — scan, query, detect drift, analyze change impact, and build a **canonical data model** from entities. Supports modern stacks (Java, TypeScript, Python) and **mainframe** (COBOL, CICS, DB2, JCL).

ArchLens treats architecture as **data extracted from code** using tree-sitter AST parsing (plus regex parsers for COBOL/JCL). It builds a C4-compatible model in SQLite and exposes a CLI (and optional MCP server) for CI and AI assistants.

## Features

- **Multi-language extraction** — Java/Spring, TypeScript/React/NestJS, Python/FastAPI
- **Mainframe extraction** — COBOL programs (CALL, EXEC CICS, EXEC SQL, COPY), JCL jobs/steps/datasets, behavioral stereotypes (UI / Service / Repository / Batch Job / Shared Data)
- **SQLite snapshots** — versioned architecture models stored in `.archlens/`
- **Canonical data model (CDM)** — tables, columns, and FK associations from Java (JPA/`I_*`), TypeScript (TypeORM), Python (SQLAlchemy/dataclass/Pydantic), and COBOL (DB2/DCLGEN) via `archlens cdm`; basic data-model inventory is also included in `archlens report`
- **Multi-repo / semantic CDM** — aggregate exports into one CDM; `.archlens/cdm.yaml` aliases, same-as, owners, suppress
- **Standalone basic data model** — `archlens data-model` inventory report (without full ER)
- **Schema ↔ CDM drift** — triangulate inferred entities against Flyway/Liquibase/DDL (`archlens schema-drift`)
- **Intent overlays** — versioned `.archlens/intents.yaml` for owners, forbidden edges, critical paths, domain boundaries
- **Process traces & domains** — API→data / CICS behavioral traces and bounded-context slicing
- **Timeline narratives** — human-readable architectural change stories between snapshots
- **Drift detection** — compare current code against the last snapshot
- **Impact analysis** — blast radius of file or component changes with graph-grounded suggestions
- **Mermaid / Structurizr diagrams** — C4 context, container, and component views
- **CI freshness** — scan + CDM + schema drift + impact artifacts on every PR (`ci/archlens-check.sh`)
- **MCP server** (optional) — tools for Claude, Copilot, Cursor, and other assistants

## Install

```bash
pip install -e ".[dev]"
# MCP is included by default; start with: archlens mcp
```

## Quick start

```bash
cd /path/to/your/repo
archlens init
archlens scan
archlens diagram --format mermaid --level component
archlens report --output docs/ARCHITECTURE.md
archlens cdm --output docs/CANONICAL_DATA_MODEL.md
# Multi-repo CDM (after per-repo export):
# archlens cdm --input billing.json --input orders.json --name Shop --output docs/CDM.md
archlens data-model --output docs/BASIC_DATA_MODEL.md
archlens schema-drift --output docs/SCHEMA_CDM_DRIFT.md
archlens traces --output docs/PROCESS_TRACES.md
archlens domains --output docs/DOMAINS.md
archlens timeline --output docs/ARCHITECTURE_TIMELINE.md
archlens impact --files path/to/changed/file.py
archlens drift --fail-on-change
```

## IDE / AI assistant setup (Phase 2)

ArchLens exposes a universal **MCP** server used by Claude Code, GitHub Copilot, Cursor, Windsurf, VS Code, and Antigravity.

```bash
pip install -e .
archlens setup-ai --platform vscode,antigravity
archlens mcp                       # stdio MCP server (default for editors)
```

| IDE / Host | Adapter files | MCP registration |
|------------|---------------|------------------|
| Claude Code | `AGENTS.md`, `.claude/mcp.json` | `archlens mcp` |
| GitHub Copilot | `.github/copilot-instructions.md`, `.vscode/settings.json` | Copilot MCP servers |
| Cursor | `.cursorrules`, `.cursor/mcp.json` | Cursor MCP |
| Windsurf | `.windsurfrules`, `.windsurf/mcp.json` | Windsurf MCP |
| VS Code | `.vscode/settings.json`, `.vscode/mcp.json` | VS Code MCP hosts |
| Antigravity | `.agents/skills/archlens/SKILL.md`, plugin under `archlens-plugin/` | MCP + skills |

MCP tools: `archlens_scan`, `archlens_query`, `archlens_impact`, `archlens_drift`, `archlens_diagram`, `archlens_report`, `archlens_cdm`, `archlens_data_model`, `archlens_schema_drift`, `archlens_intents`, `archlens_traces`, `archlens_domains`, `archlens_timeline`, `archlens_health`, …

Interactive agent (CLI fallback if Antigravity SDK is absent):

```bash
archlens agent --repo . --cli
```

## CLI

| Command | Description |
|---------|-------------|
| `archlens init` | Initialize `.archlens/` in a repo |
| `archlens scan` | Parse codebase → create snapshot |
| `archlens diff` | Compare two snapshots |
| `archlens impact` | Analyze impact of changed files |
| `archlens diagram` | Generate Mermaid/Structurizr diagrams |
| `archlens report` | Generate `ARCHITECTURE.md` |
| `archlens query` | Query the architecture DB |
| `archlens drift` | Check for architectural drift |
| `archlens export` | Export architecture as JSON |
| `archlens mcp` | Start MCP server for AI assistants / IDEs |
| `archlens setup-ai` | Generate platform adapter files for all IDEs |
| `archlens agent` | Interactive architect agent (Antigravity or CLI) |
| `archlens aggregate` | Merge multi-repo `architecture.json` exports |
| `archlens events` | Detect Kafka/RabbitMQ/SQS producers & consumers |
| `archlens contracts` | Link services via OpenAPI + HTTP call sites |
| `archlens health` | Score coupling, cycles, layer violations |
| `archlens cdm` | Generate CDM (tables/columns/FKs); supports `--input` multi-repo + `.archlens/cdm.yaml` semantics |
| `archlens data-model` | Standalone basic data-model inventory (no full ER) |
| `archlens schema-drift` | Compare CDM vs Flyway/Liquibase/DDL |
| `archlens intents` | Validate `.archlens/intents.yaml` overlays |
| `archlens traces` | Behavioral API→data / CICS process traces |
| `archlens domains` | Domain / bounded-context slices |
| `archlens timeline` | Narrative time-travel diff between snapshots |
| `archlens federate` | Fetch remote architecture JSON / HTTP export |

## Phase 3 (distributed)

```bash
# Per-repo exports
archlens scan && archlens export --output billing.json
# Aggregate
archlens aggregate --input billing.json --input orders.json --name "Shop" --output system.json
# Events / contracts / health
archlens events
archlens contracts --repos ./billing,./orders
archlens health
archlens federate --url https://example.com/architecture.json
```

## Configuration

Create `.archlens.yaml` in the repo root (or run `archlens init`). See the generated file for stereotype mappings, include/exclude paths, and impact settings.

## License

MIT
