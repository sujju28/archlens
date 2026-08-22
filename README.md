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
- **Capabilities catalog** — scan auto-seeds `.archlens/capabilities.yaml` from entry points; teams curate titles/owners (`archlens capabilities`)
- **Playbooks / explain** — reading path, blast radius, tests, plus grounded explain from citations (`archlens playbook`, `archlens explain`; optional LLM via `OPENAI_API_KEY` / `ARCHLENS_LLM_API_KEY`)
- **Comments & candidate rules** — Javadoc/remarks and IF/EVALUATE/validators listed per capability (`archlens rules`)
- **Fine grain** — COBOL paragraphs/PERFORM, Java/Python methods, BMS fields, COPY usage (`archlens grain`)
- **Strangler slice** — programs + tables + jobs + maps to extract together (`archlens strangler`)
- **Reading priority** — hotspots to learn first vs isolated/unreachable (`archlens reading-priority`)
- **Ops overlay** — JCL jobs/steps, CICS TRANSID, BMS maps (`archlens ops`)
- **Onboarding mode** — 90-minute path: context → 10 capabilities → one guided change (`archlens onboard`)
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
archlens capabilities --output docs/CAPABILITIES.md
archlens playbook --capability UserController --output docs/PLAYBOOKS.md
archlens explain --capability UserController --no-llm
archlens onboard --output docs/ONBOARDING.md
archlens strangler --capability UserController
archlens grain --capability UserController
archlens rules --capability UserController
archlens ops
archlens reading-priority
archlens schema-drift --output docs/SCHEMA_CDM_DRIFT.md
archlens traces --output docs/PROCESS_TRACES.md
archlens domains --output docs/DOMAINS.md
archlens timeline --output docs/ARCHITECTURE_TIMELINE.md
archlens impact --files path/to/changed/file.py
archlens drift --fail-on-change
```

## IDE / AI assistant setup

Skills and the Architect workflow **ship in ArchLens**. On a target repo you only enable them:

```bash
pip install -e /path/to/archlens   # or pip install archlens
cd /path/to/your/app
archlens init                      # also installs Cursor MCP + skills
# all IDEs:
archlens setup-ai --platform all --overwrite
archlens mcp                       # stdio MCP (editors start this via mcp.json)
```

`setup-ai` copies packaged skills into **your app repo**:

- `.cursor/skills/archlens-*` (Cursor)
- `.claude/skills/archlens-*` (Claude Code)
- `.agents/skills/archlens-*` (Antigravity)
- MCP: `.cursor/mcp.json`, `.claude/mcp.json`, …

Team members do not write prompts. They ask “what breaks if I change COACTUPC?” and the project skills route to MCP.

| IDE / Host | Adapter files | MCP registration |
|------------|---------------|------------------|
| Claude Code | `AGENTS.md`, `.claude/mcp.json`, `.claude/skills/` | `archlens mcp` |
| GitHub Copilot | `.github/copilot-instructions.md`, `.vscode/settings.json` | Copilot MCP servers |
| Cursor | `.cursorrules`, `.cursor/rules/archlens.mdc`, `.cursor/mcp.json`, `.cursor/skills/` | Cursor MCP |
| Windsurf | `.windsurfrules`, `.windsurf/mcp.json` | Windsurf MCP |
| VS Code | `.vscode/settings.json`, `.vscode/mcp.json` | VS Code MCP hosts |
| Antigravity | `.agents/skills/`, plugin under `archlens-plugin/` | MCP + skills |

Canonical skill source (this repo): `archlens/skills/`. Named jobs: **scan**, **onboard**, **change**, **impact**, **data**, **legacy**, **drift**, plus **architect** routing.

MCP tools: `archlens_scan`, `archlens_query`, `archlens_impact`, `archlens_drift`, `archlens_diagram`, `archlens_report`, `archlens_cdm`, `archlens_data_model`, `archlens_capabilities`, `archlens_playbook`, `archlens_explain`, `archlens_strangler`, `archlens_grain`, `archlens_onboard`, `archlens_rules`, `archlens_ops`, `archlens_reading_priority`, `archlens_schema_drift`, `archlens_intents`, `archlens_traces`, `archlens_domains`, `archlens_timeline`, `archlens_health`, …

Interactive agent (CLI fallback if Antigravity SDK is absent):

```bash
archlens agent --repo . --cli
```

## CLI

| Command | Description |
|---------|-------------|
| `archlens init` | Initialize `.archlens/` plus Cursor MCP and skills |
| `archlens scan` | Parse codebase → create snapshot |
| `archlens setup-ai` | Install MCP adapters and ArchLens skills for IDEs |
| `archlens diff` | Compare two snapshots |
| `archlens impact` | Analyze impact of changed files |
| `archlens diagram` | Generate Mermaid/Structurizr diagrams |
| `archlens report` | Generate `ARCHITECTURE.md` |
| `archlens query` | Query the architecture DB |
| `archlens drift` | Check for architectural drift |
| `archlens export` | Export architecture as JSON |
| `archlens mcp` | Start MCP server for AI assistants / IDEs |
| `archlens agent` | Interactive architect agent (Antigravity or CLI) |
| `archlens aggregate` | Merge multi-repo `architecture.json` exports |
| `archlens events` | Detect Kafka/RabbitMQ/SQS producers & consumers |
| `archlens contracts` | Link services via OpenAPI + HTTP call sites |
| `archlens health` | Score coupling, cycles, layer violations |
| `archlens cdm` | Generate CDM (tables/columns/FKs); supports `--input` multi-repo + `.archlens/cdm.yaml` semantics |
| `archlens data-model` | Standalone basic data-model inventory (no full ER) |
| `archlens capabilities` | Hybrid capability catalog (scan-seeded, human-curated labels) |
| `archlens playbook` | Reading path + change recipe for a capability |
| `archlens explain` | Grounded explanation from citations (optional LLM) |
| `archlens onboard` | 90-minute onboarding guide |
| `archlens strangler` | Extract slice (programs/tables/jobs/maps) |
| `archlens grain` | Paragraph/PERFORM/method/BMS/COPY grain |
| `archlens rules` | Candidate rules + comments as documentation |
| `archlens ops` | JCL / CICS TRANSID / BMS overlay |
| `archlens reading-priority` | Hotspots vs skip/unreachable |
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
