# ArchLens

Living architecture intelligence for any codebase — scan, query, detect drift, and analyze the impact of changes.

ArchLens treats architecture as **data extracted from code** using tree-sitter AST parsing. It builds a C4-compatible model in SQLite and exposes a CLI (and optional MCP server) for CI and AI assistants.

## Features

- **Multi-language extraction** — Java/Spring, TypeScript/React/NestJS, Python/FastAPI
- **SQLite snapshots** — versioned architecture models stored in `.archlens/`
- **Drift detection** — compare current code against the last snapshot
- **Impact analysis** — blast radius of file or component changes
- **Mermaid / Structurizr diagrams** — C4 context, container, and component views
- **CI-ready** — platform-agnostic check script + GitHub Actions / GitLab CI examples
- **MCP server** (optional) — tools for Claude, Copilot, Cursor, and other assistants

## Install

```bash
pip install -e ".[dev]"
# Optional MCP support:
pip install -e ".[mcp]"
```

## Quick start

```bash
cd /path/to/your/repo
archlens init
archlens scan
archlens diagram --format mermaid --level component
archlens report --output docs/ARCHITECTURE.md
archlens impact --files path/to/changed/file.py
archlens drift --fail-on-change
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
| `archlens mcp` | Start MCP server for AI assistants |
| `archlens setup-ai` | Generate platform adapter files |

## Configuration

Create `.archlens.yaml` in the repo root (or run `archlens init`). See the generated file for stereotype mappings, include/exclude paths, and impact settings.

## License

MIT
