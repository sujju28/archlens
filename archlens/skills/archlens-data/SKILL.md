---
name: archlens-data
description: >-
  Answers data-model, table, COPY, CDM, and schema-drift questions using
  ArchLens. Use when the user asks about entities, tables, FKs, DCLGEN,
  Flyway/Liquibase drift, or the canonical data model.
---

# ArchLens data

Read [../_shared.md](../_shared.md). Scan first if stale.

## Steps
Pick the tool that matches the question:
- Inventory / ER: `archlens_cdm` or `archlens_data_model`
- DDL vs inferred model: `archlens_schema_drift`
- COPY / tables on a feature: `archlens_playbook` or `archlens_grain` for that capability

Cite table/COPY names from the tool. Do not invent columns or FKs.
