---
name: archlens-onboard
description: >-
  Runs the first-90-minutes ArchLens onboarding path: context, capabilities,
  one guided change. Use when the user is new to the repo, asks how to get
  started, onboarding, where to begin, or "explain this codebase" at a high
  level.
---

# ArchLens onboard

Read [../_shared.md](../_shared.md). Scan first if the snapshot may be stale (`archlens-scan`).

## Steps
1. MCP `archlens_onboard` with `repo_path` (optional `capability` if they named one).
2. Summarize: context (languages/containers), the 10 capabilities, the suggested first change.
3. Offer next: playbook / explain / impact on that capability — do not start a large refactor from onboard alone.

CLI: `archlens onboard --repo <root> --output docs/ONBOARDING.md`
