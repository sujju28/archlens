---
name: archlens-impact
description: >-
  Analyze the impact of code changes or new requirements on the architecture.
  Use when the user asks "what is the impact of changing X", "what will this PR break",
  or "estimate the effort for this change".
---

# ArchLens Impact Analysis Skill

## Workflow
1. Ensure fresh snapshot (archlens-scan)
2. Run structural impact:
```bash
python <skill_dir>/scripts/analyze_impact.py --repo-path <repo_root> --files <files...> --output json
```
3. Suggest changes:
```bash
python <skill_dir>/scripts/suggest_changes.py --repo-path <repo_root> --impact-json <path>
```
4. Estimate effort:
```bash
python <skill_dir>/scripts/estimate_effort.py --repo-path <repo_root> --impact-json <path>
```

## Rules
- Always show dependency chains
- Distinguish direct vs transitive impact
- Be conservative with estimates
