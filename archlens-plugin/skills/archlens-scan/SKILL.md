---
name: archlens-scan
description: >-
  Scan a codebase to extract its architecture model. Use when the user asks to
  "scan", "analyze the architecture of", "build an architecture model for",
  or "map" a repository. Also use when a fresh snapshot is needed before
  running queries or impact analysis.
---

# ArchLens Scan Skill

## Prerequisites
- The `archlens` CLI must be installed: `pip install archlens`

## Workflow

### Step 1: Check if ArchLens is initialized
Run: `ls .archlens/` in the repo root.
- If `.archlens/` does not exist, run: `archlens init`

### Step 2: Check snapshot freshness
```bash
python <skill_dir>/scripts/check_freshness.py --repo-path <repo_root>
```

### Step 3: Scan the codebase
```bash
archlens scan --commit $(git -C <repo_root> rev-parse HEAD) --repo <repo_root>
```

### Step 4: Generate a quick overview diagram
```bash
archlens diagram --format mermaid --level component --repo <repo_root>
```
