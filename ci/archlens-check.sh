#!/usr/bin/env bash
# ArchLens CI check — freshness, drift, impact, CDM, schema triangulation
set -euo pipefail

REPO_ROOT="${1:-.}"
cd "$REPO_ROOT"

CI_COMMIT_SHA="${CI_COMMIT_SHA:-${GITHUB_SHA:-$(git rev-parse HEAD 2>/dev/null || echo unknown)}}"
BASE_REF="${ARCHLENS_BASE_REF:-origin/main}"

echo "==> ArchLens CI check"
echo "    Commit: $CI_COMMIT_SHA"

if ! command -v archlens >/dev/null 2>&1; then
  pip install archlens || pip install -e .
fi

if [[ ! -d .archlens ]]; then
  archlens init --repo .
fi

# Freshness: always rescan HEAD
archlens scan --repo . --commit "$CI_COMMIT_SHA"

# Architectural drift vs previous snapshot
if [[ "${ARCHLENS_FAIL_ON_DRIFT:-0}" == "1" ]]; then
  archlens drift --repo . --fail-on-change || {
    echo "Architectural drift detected"
    exit 2
  }
else
  archlens drift --repo . || true
fi

# Intent overlay validation (forbidden edges / missing critical path elements)
if [[ "${ARCHLENS_VALIDATE_INTENTS:-1}" == "1" ]]; then
  archlens intents --repo . --validate || {
    if [[ "${ARCHLENS_FAIL_ON_INTENTS:-0}" == "1" ]]; then
      exit 2
    fi
  }
fi

# Impact report for PR changed files
if git rev-parse "$BASE_REF" >/dev/null 2>&1; then
  CHANGED_FILES=$(git diff --name-only "${BASE_REF}...HEAD" || true)
  if [[ -n "${CHANGED_FILES}" ]]; then
    # shellcheck disable=SC2086
    archlens impact --repo . --files $CHANGED_FILES --output impact_report.md || true
  fi
fi

mkdir -p docs
archlens report --repo . --output docs/ARCHITECTURE.md
archlens cdm --repo . --output docs/CANONICAL_DATA_MODEL.md || true
archlens schema-drift --repo . --output docs/SCHEMA_CDM_DRIFT.md || true
archlens traces --repo . --output docs/PROCESS_TRACES.md || true
archlens domains --repo . --output docs/DOMAINS.md || true

# Optional hard fail on CDM↔schema drift
if [[ "${ARCHLENS_FAIL_ON_SCHEMA_DRIFT:-0}" == "1" ]]; then
  archlens schema-drift --repo . --fail-on-drift --output docs/SCHEMA_CDM_DRIFT.md
fi

# Narrative timeline when ≥2 snapshots exist
archlens timeline --repo . --output docs/ARCHITECTURE_TIMELINE.md || true

echo "==> ArchLens check complete"
echo "    Artifacts: docs/ARCHITECTURE.md docs/CANONICAL_DATA_MODEL.md impact_report.md"
