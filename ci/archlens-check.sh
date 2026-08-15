#!/usr/bin/env bash
# ArchLens CI check — platform-agnostic
set -euo pipefail

REPO_ROOT="${1:-.}"
cd "$REPO_ROOT"

CI_COMMIT_SHA="${CI_COMMIT_SHA:-${GITHUB_SHA:-$(git rev-parse HEAD 2>/dev/null || echo unknown)}}"
BASE_REF="${ARCHLENS_BASE_REF:-origin/main}"

echo "==> ArchLens CI check"
echo "    Commit: $CI_COMMIT_SHA"

# 1. Ensure package available (prefer already-installed)
if ! command -v archlens >/dev/null 2>&1; then
  pip install archlens || pip install -e .
fi

# 2. Initialize if needed
if [[ ! -d .archlens ]]; then
  archlens init --repo .
fi

# 3. Scan current state
archlens scan --repo . --commit "$CI_COMMIT_SHA"

# 4. Drift check (non-fatal unless ARCHLENS_FAIL_ON_DRIFT=1)
if [[ "${ARCHLENS_FAIL_ON_DRIFT:-0}" == "1" ]]; then
  archlens drift --repo . --fail-on-change || {
    echo "Architectural drift detected"
    exit 2
  }
else
  archlens drift --repo . || true
fi

# 5. Impact report for PR
if git rev-parse "$BASE_REF" >/dev/null 2>&1; then
  CHANGED_FILES=$(git diff --name-only "${BASE_REF}...HEAD" || true)
  if [[ -n "${CHANGED_FILES}" ]]; then
    archlens impact --repo . --files $CHANGED_FILES --output impact_report.md || true
  fi
fi

# 6. Architecture report
mkdir -p docs
archlens report --repo . --output docs/ARCHITECTURE.md

echo "==> ArchLens check complete"
