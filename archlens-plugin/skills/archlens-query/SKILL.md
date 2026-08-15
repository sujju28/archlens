---
name: archlens-query
description: >-
  Query the architecture database to answer questions about the codebase structure.
  Use when the user asks "what depends on X", "show me all services",
  "what calls UserService", or any question about code organization or dependencies.
---

# ArchLens Query Skill

## Prerequisites
- A scan must have been run first.

## Helper Scripts
```bash
python <skill_dir>/scripts/list_elements.py --repo-path <repo_root> --stereotype Controller
python <skill_dir>/scripts/show_dependencies.py --repo-path <repo_root> --element UserService --direction upstream
python <skill_dir>/scripts/query_arch.py --repo-path <repo_root> --query "what depends on UserService"
```
