---
name: archlens-drift
description: >-
  Detect architectural drift between the current codebase and the last known snapshot.
  Use when the user asks "has the architecture changed" or "is the documentation up to date".
---

# ArchLens Drift Detection Skill

```bash
python <skill_dir>/scripts/detect_drift.py --repo-path <repo_root> --output json
python <skill_dir>/scripts/generate_diff_report.py --repo-path <repo_root> --output markdown
```

If drift is detected and the user wants docs updated, run `archlens report`.
