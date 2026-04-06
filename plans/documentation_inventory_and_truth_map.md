# Documentation Inventory And Truth Map

## Status: Active Inventory

Reviewed against the repository state on 2026-04-06.

This file exists to reduce documentation drift during the codebase refactor and
docs catch-up plan.

Use it to answer:

- which docs are canonical
- which docs are summaries
- which docs are plans
- which docs are historical/reference-only
- which docs must be updated when implementation changes

---

## Truth Order

When implementation changes, update docs in this order:

1. planning doc for the intended change
2. implementation
3. canonical contract/reference docs
4. author-facing workflow docs
5. summary/status docs
6. changelog

If a planning doc still reads like active truth after the implementation lands,
either update it to match reality or mark it clearly as historical/outdated.

---

## Top-Level Engine Docs

| Path | Status | Role | Must Match Code Closely? | Notes |
|---|---|---|---|---|
| `PROJECT_SPIRIT.md` | Active direction | Design compass / philosophy | No, but should reflect current direction | High-level intent, not implementation detail |
| `README.md` | Active summary | Project overview, quick start, current capabilities | Yes, at summary level | Should not overstate or understate runtime/editor capability |
| `AUTHORING_GUIDE.md` | Active author-facing doc | How to build content against the current system | Yes | Should track real authoring workflows and surfaces |
| `ENGINE_JSON_INTERFACE.md` | Active canonical reference | Current engine <-> JSON contract | Yes, strictly | Primary source for exact current JSON shape and command surface |
| `architecture.md` | Active explanatory doc | Architecture and medium-term direction | Yes, at architectural level | Can include direction, but must not contradict implemented boundaries |
| `CONTRIBUTING.md` | Active contributor guidance | Working rules and update expectations | Yes | Should describe doc/update/test expectations accurately |
| `CHANGELOG.md` | Active historical summary | Reverse-chronological feature/change log | Yes | Should reflect shipped changes, not plans |
| `roadmap.md` | Active planning summary | Future direction | No | Must not be mistaken for current engine/editor contract |
| `AGENTS.md` | Active onboarding doc | Agent instructions and repo entry point | Yes | Must reflect current workflow and validation expectations |

---

## Plans Folder

Everything under `plans/` should be treated as planning material unless a file
explicitly says otherwise.

General rule:

- plans may describe intended future structure
- plans must not silently replace canonical docs as current truth
- if a plan is obsolete but still useful, leave it as planning history and keep
  the active truth in the canonical docs

Key active planning docs:

| Path | Status | Role | Must Match Code Closely? | Notes |
|---|---|---|---|---|
| `plans/codebase_refactor_and_docs_catchup_plan.md` | Active plan | Refactor and docs roadmap | Yes, as a plan | Governs the current refactor sequence |
| `plans/documentation_inventory_and_truth_map.md` | Active inventory | Doc classification and update order | Yes | Supports the docs catch-up track |
| `plans/codebase_health_fixes.md` | Historical plan | Earlier health-fix inventory | No | Useful reference; not active truth |
| `plans/engine_rework_direction.md` | Active direction plan | Architectural direction for rework | No, but should remain directionally aligned | Planning truth, not contract truth |
| Other files in `plans/` | Planning / historical | Feature and architecture planning | No | Consult as intent/reference, not as canonical contract |

---

## Editor Docs

| Path | Status | Role | Must Match Code Closely? | Notes |
|---|---|---|---|---|
| `tools/area_editor/README.md` | Active summary | Editor overview, current capabilities, limits | Yes | Primary summary of current editor status |
| `tools/area_editor/ARCHITECTURE.md` | Active architecture note | Current editor architecture plus intended shape | Yes | Must not describe already-implemented surfaces as still entirely planned |
| `tools/area_editor/AGENTS.md` | Active tool onboarding | Tool-specific working rules | Yes | Must preserve the editor/runtime boundary |
| `tools/area_editor/DATA_BOUNDARY.md` | Active boundary note | Tool/runtime separation rules | Yes | Important for refactors touching shared helpers |
| `tools/area_editor/DECISIONS.md` | Active decision log | Tool architectural decisions | Yes, at policy level | Can include rationale beyond current implementation details |
| `tools/area_editor/ROADMAP.md` | Active planning summary | Editor future work | No | Must not be confused with current capability |
| `tools/area_editor/FUTURE_FEATURES.md` | Active planning summary | Known editor gaps/future ideas | No | Should stay clearly future-facing |
| `tools/area_editor/SCOPE.md` | Active summary | Tool scope and non-goals | Yes | Should stay aligned with the current boundary |
| `tools/area_editor/VISION.md` | Active direction | High-level editor goals | No | Directional document |
| `tools/area_editor/OPEN_QUESTIONS.md` | Active planning note | Unresolved questions | No | Planning material |
| `tools/area_editor/PHASE1_PLAN.md` | Historical plan | Early implementation planning | No | Historical/planning reference |
| `tools/area_editor/PHASE2_PLAN.md` | Historical plan | Early implementation planning | No | Historical/planning reference |
| `tools/area_editor/PHASE3_TILE_PAINTING_PLAN.md` | Historical plan | Earlier feature planning | No | Historical/planning reference |
| `tools/area_editor/PHASE4_IMPLEMENTATION_PLAN.md` | Active plan | Later implementation plan | No | Planning truth only |
| `tools/area_editor/PHASE4_UX_PLAN.md` | Active plan | UX planning | No | Planning truth only |
| `tools/area_editor/*_PLAN.md` | Planning / historical | Feature planning docs | No | Keep separate from current-state docs |

---

## Historical / Reference-Only Areas

| Path | Status | Role | Must Match Code Closely? | Notes |
|---|---|---|---|---|
| `archived_editor/` | Historical reference | Archived old built-in editor | No | Not part of the active codebase |
| `archive/` | Historical/reference | Archived material | No | Treat as non-active unless explicitly revived |

---

## Update Checklist By Change Type

### If the JSON contract changes

Review and update:

- `ENGINE_JSON_INTERFACE.md`
- `AUTHORING_GUIDE.md`
- `README.md`
- `CHANGELOG.md`
- relevant editor docs if the editor surface or support expectations changed

### If command behavior or command validation changes

Review and update:

- `ENGINE_JSON_INTERFACE.md`
- `AUTHORING_GUIDE.md`
- `README.md`
- `CHANGELOG.md`
- `CONTRIBUTING.md` if contributor workflow changed
- editor docs if structured editing or validation assumptions changed

### If project manifest/content-id/path rules change

Review and update:

- `ENGINE_JSON_INTERFACE.md`
- `AUTHORING_GUIDE.md`
- `README.md`
- `architecture.md`
- `tools/area_editor/README.md`
- `tools/area_editor/ARCHITECTURE.md`
- `tools/area_editor/DATA_BOUNDARY.md` if the shared boundary changes

### If editor workflows or supported surfaces change

Review and update:

- `tools/area_editor/README.md`
- `tools/area_editor/ARCHITECTURE.md`
- `README.md`
- `CHANGELOG.md`
- any relevant tool planning/status docs if they now misstate reality

### If only internal structure changes

Still review:

- `architecture.md`
- `tools/area_editor/ARCHITECTURE.md`
- `CONTRIBUTING.md`
- any onboarding docs that mention file ownership or workflow

Even if behavior does not change, large refactors can make docs stale if they
mention old module boundaries.

---

## Current Known Drift To Resolve Early

These were already identified during the initial review:

- `tools/area_editor/ARCHITECTURE.md` understates the currently implemented
  editor surface and still reads partly like a much earlier phase snapshot.

Potential follow-up audit targets:

- `README.md` versus editor docs for wording around current editor limitations
- `architecture.md` versus newer engine-owned runtime sessions and current
  command-surface reality
- any plan files that are easy to misread as active current-state docs

---

## Working Rule

When a refactor step changes code:

1. identify which docs in this inventory are affected
2. update those docs before moving to the next risky step
3. if docs disagree and the correct behavior is unclear, stop and resolve the
   ambiguity before continuing
