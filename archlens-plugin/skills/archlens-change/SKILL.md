---
name: archlens-change
description: >-
  Guides a first or follow-on code change using ArchLens playbooks and
  grounded explain. Use when the user wants to change a feature, capability,
  screen, program, or class, asks what to read first, how to implement X, or
  "where do I start to change Y".
---

# ArchLens change

Read [../_shared.md](../_shared.md). Scan first if stale.

## Steps
1. MCP `archlens_capabilities` to resolve the capability (id, title, or element name).
2. MCP `archlens_playbook` with that `capability`.
3. MCP `archlens_explain` with `no_llm: true` unless the user asks for LLM prose (`no_llm: false` only then).
4. MCP `archlens_impact` on the files or elements they will edit.
5. Tell them to run the playbook's listed tests. Do not invent extra tests.

Optional: `archlens_grain` / `archlens_rules` if they need paragraphs, COPY, or candidate IFs.

Never describe business meaning that is not in citations or curated capability title/description.
