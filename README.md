# ArchLens

Living architecture intelligence for any codebase — scan, query, detect drift, analyze change impact, and build a **canonical data model** from entities. Supports modern stacks (Java, TypeScript, Python) and **mainframe** (COBOL, CICS, DB2, JCL).

ArchLens treats architecture as **data extracted from code** using tree-sitter AST parsing (plus regex parsers for COBOL/JCL). It builds a C4-compatible model in SQLite and exposes a CLI (and optional MCP server) for CI and AI assistants.

## Features

- **Multi-language extraction** — Java/Spring, TypeScript/React/NestJS, Python/FastAPI
- **Mainframe extraction** — COBOL programs (CALL, EXEC CICS, EXEC SQL, COPY), JCL jobs/steps/datasets, behavioral stereotypes (UI / Service / Repository / Batch Job / Shared Data)
- **SQLite snapshots** — versioned architecture models stored in `.archlens/`
- **Canonical data model (CDM)** — infer tables, columns, and FK associations from JPA `@Entity` and Adempiere/metasfresh `I_*` / `X_*` PO models (`archlens cdm`)
- **Drift detection** — compare current code against the last snapshot
- **Impact analysis** — blast radius of file or component changes
- **Mermaid / Structurizr diagrams** — C4 context, container, and component views
- **CI-ready** — platform-agnostic check script + GitHub Actions / GitLab CI examples
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

MCP tools: `archlens_scan`, `archlens_query`, `archlens_impact`, `archlens_drift`, `archlens_diagram`, `archlens_report`, `archlens_cdm`, `archlens_health`, …

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
| `archlens cdm` | Generate canonical data model from Entity/PO/JPA types |
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
