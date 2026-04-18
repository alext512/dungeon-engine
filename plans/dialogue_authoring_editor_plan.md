# Dialogue Authoring Editor Plan

This document captures the current agreed implementation direction for dialogue
authoring in the external editor.

It is a planning document, not canonical engine truth. Canonical behavior lives
in runtime code, validation, tests, and the authoring docs after the relevant
changes are implemented.

This plan is intentionally practical. It records:

- what already exists
- what decisions are already settled
- what still needs to be built
- the order that work should happen
- where the boundaries should stay clean between dialogue-owned data and
  caller-owned overrides

It should be read alongside:

- `plans/dialogue_choice_authoring_model.md`
- `plans/dialogue_ui_rework_direction.md`

## Scope

This plan covers:

- inline `dialogue_definition` support
- the external editor workflow for editing dialogue definitions
- command authoring inside dialogues
- the likely next-step branch authoring model for dialogue choices

This plan does not try to redesign the entire dialogue runtime or the full
future dialogue UI system. It is focused on making current dialogue authoring
usable and scalable without throwing away the existing runtime model.

## Current State

### Runtime and Contract

Implemented:

- `open_dialogue_session` supports exactly one of:
  - `dialogue_path`
  - `dialogue_definition`
- `dialogue_definition` is treated as a deferred command-bearing payload
- `parameter_specs.type: "dialogue_definition"` exists
- runtime validation, docs, and tests understand inline dialogue definitions

### Editor

Implemented:

- entity parameters with type `dialogue_definition` can be opened through an
  `Edit...` entry in the entity instance dialog
- dedicated dialogue popup for editing one dialogue definition
- structured segment list editor
- structured option list editor for choice segments
- right-click add/delete for segments and options
- drag reorder for segments and options
- dedicated command-list popup for dialogue-owned command lists
- searchable Add Command dialog
- dialogue-context suggestions in the command picker
- custom editor for `open_dialogue_session`
- `ui_preset`, `actor_id`, and `caller_id` grouped under `Advanced` for
  `open_dialogue_session`

### Sample Content

Implemented:

- `sign_v2` sample content exists to exercise inline dialogue-definition
  authoring

## Decisions Already Made

These points are already settled enough to build around.

### 1. Dialogue definitions and dialogue files should use the same schema

Inline dialogue should not be a smaller or alternate mini-format.

If the engine accepts a dialogue definition inline, it should support the same
segment and option structure as file-backed dialogue data.

### 2. The entity instance dialog should stay relatively clean

The entity instance dialog should not try to become a full nested dialogue and
command workbench.

Instead:

- the entity dialog owns the entity
- the dialogue popup owns one dialogue definition
- the command popup owns one command list

This keeps dirty state and authoring responsibility understandable.

### 3. The dialogue popup should only own dialogue-authored behavior

Inside a dialogue definition, the editor should expose:

- segment `on_start`
- segment `on_end`
- choice option `commands`

The dialogue popup should not expose caller-owned override mechanisms like:

- `dialogue_on_start`
- `dialogue_on_end`
- `segment_hooks`

Those belong to the editor for the `open_dialogue_session` command, because
they customize a specific invocation of the dialogue rather than the dialogue
definition itself.

### 4. Hooks are valid, but they are advanced

`segment_hooks` are not considered bad design, but they should remain an
advanced override/reuse mechanism rather than the everyday way authors express
dialogue behavior.

The preferred default is:

- dialogue-owned behavior lives in the dialogue
- caller-owned overrides live on the caller

### 5. The editor should reduce complexity before the runtime is redesigned

The current runtime already supports branching through command-driven child
dialogues. The editor should first make that model feel usable before any major
runtime redesign is attempted.

## Problem Statement

The current system is already powerful enough to express:

- linear dialogue
- choice options
- per-segment command hooks
- nested inline child dialogues
- file-backed child dialogues

But the authoring model becomes hard to follow because branching currently lives
inside generic command lists.

That creates three practical issues:

1. common dialogue branching feels more technical than it should
2. nested popups can become hard to track when one choice opens another
   dialogue definition
3. the editor cannot easily distinguish "this option branches to another
   dialogue" from "this option runs arbitrary custom gameplay commands"

## Target Authoring Model

The editor should eventually make the common path feel like this:

- write dialogue segments
- add a choice
- define each option
- optionally attach commands
- optionally continue into another dialogue branch

The common branching case should feel like dialogue authoring, not like generic
command surgery.

At the same time, the system must preserve advanced flexibility:

- option commands still need to exist
- segment commands still need to exist
- reusable caller hooks still need to exist
- raw JSON escape hatches still need to exist

## Proposed Implementation Phases

### Phase 1: Foundation (Implemented)

Completed:

- inline `dialogue_definition` runtime support
- validation/docs/tests for inline dialogue definitions
- entity parameter entry point for editing dialogue definitions
- dialogue popup
- command-list popup
- `open_dialogue_session` special-case editor

This phase proved the data model and UI nesting can work end-to-end.

### Phase 2: Command Popup Maturation

Goal:

- make the command popup useful for ordinary authoring without forcing raw JSON
  for most common tasks

Deliverables:

- typed editors for the most common dialogue-related commands first:
  - `open_dialogue_session`
  - `run_project_command`
  - `set_entity_var`
  - `set_current_area_var`
  - `close_dialogue_session`
- reference pickers where appropriate:
  - dialogue file picker
  - command picker
  - entity picker
  - area picker when relevant
- preserve `Command JSON` and/or `Parameters JSON` fallback for uncommon fields

Notes:

- this should be curated command-by-command, not by inventing a fake generic UI
  schema that guesses too much
- `Advanced` grouping should be curated only where it clearly helps

### Phase 3: Dialogue Popup Polish

Goal:

- make the dialogue popup stable and pleasant for frequent use

Deliverables:

- duplicate segment / duplicate option actions if needed
- better summary text for segments and commands
- keyboard support for selection, deletion, and reordering
- explicit dirty-state prompts where nested dialog editing is involved
- optional preview summary for nested child dialogues

Possible later additions:

- richer summaries like:
  - `2 commands`
  - `child dialogue: 3 segments`
  - `branch + commands`

### Phase 4: First-Class Choice Branch Fields

Goal:

- make the common "this option continues into another dialogue" case easier to
  author and easier for the editor to understand

Proposed additive authored fields on a choice option:

- `next_dialogue_definition`
- `next_dialogue_path`

Recommended rules:

- zero or one of `next_dialogue_definition` / `next_dialogue_path`
- `commands` remain valid and continue to exist
- execution order should be:
  1. run option `commands`
  2. open `next_dialogue_*` if present
  3. when that child dialogue closes, finish the current segment normally

Why additive is preferred:

- authors can still perform side effects and then branch
- no existing power is lost
- the editor gets a much clearer signal for the common branching case

Why this matters:

- it lets the editor present dialogue branching as dialogue structure
- it removes the need to infer every branch from arbitrary command JSON
- it makes later tree-based or graph-like navigation much easier

Required work if implemented:

- runtime support
- audit/validation updates
- authoring docs
- editor support
- focused tests
- sample content coverage

### Phase 5: Tree-Aware Dialogue Workspace

Goal:

- reduce popup recursion and make nested dialogue branches easier to navigate

Preferred direction:

- keep the current popup architecture
- add a tree or outline view inside the dialogue editor for dialogue-owned
  branches

Example shape:

- Main Dialogue
  - Segment 1
  - Segment 2
    - Option `Front` -> Child Dialogue
    - Option `Back` -> Child Dialogue

This should only be attempted after Phase 4 or after the editor can reliably
recognize branch-like child dialogues.

Without a first-class branch field, the editor would be forced to reverse-engineer
arbitrary command lists, which is fragile.

### Phase 6: Dialogue File Editing Reuse

Goal:

- reuse the same dialogue editor for project dialogue files, not only inline
  dialogue-definition parameters

Deliverables:

- open a dialogue JSON file in the same structured popup/editor surface
- preserve unknown fields through round-trips
- support switching between structured and raw JSON editing
- use the same nested branch editing model as inline dialogue definitions

This is a strong reuse opportunity:

- one dialogue object editor
- multiple entry points:
  - entity parameter
  - command-owned inline child dialogue
  - standalone project dialogue file

### Phase 7: Caller-Hook Authoring in Command Editor

Goal:

- support advanced reusable-dialogue workflows cleanly without polluting the
  dialogue-definition popup

Deliverables:

- in the `open_dialogue_session` command editor, expose:
  - `dialogue_on_start`
  - `dialogue_on_end`
  - `segment_hooks`
- likely group these in `Advanced`
- provide summaries rather than dumping raw nested JSON by default

Important:

- this work should happen only after the dialogue-owned editing path is solid
- hooks are important, but they are not the first thing authors need

## Editor Rules To Preserve

These rules should remain true throughout future work.

### Preserve unknown data

If the structured editor does not own a field, it must survive saves.

This matters for:

- future dialogue fields
- rare command parameters
- custom metadata

### Keep JSON escape hatches

Structured editors should become the default path, not the only path.

Every major subtree editor should retain a raw JSON fallback:

- dialogue definition
- command list
- command params when needed

### Avoid inventing editor-only authored data

The editor should not create a separate fake dialogue model just for itself.

If a UI concept is useful, prefer mapping it onto stable authored JSON that the
runtime and validation layers also understand.

### Keep boundaries clear

- dialogue popup edits dialogue-owned data
- command popup edits command-owned data
- caller hooks live with the caller command, not with the dialogue definition

## Test and Validation Expectations

Whenever future phases change the dialogue authoring contract, update all of:

- runtime behavior
- startup validation
- command audit behavior
- authoring docs
- editor handling
- focused tests
- sample content coverage notes

Recommended verification for substantive dialogue/editor phases:

```text
.venv/Scripts/python -m unittest discover -s tests -v
cd tools/area_editor
..\..\.venv/Scripts/python -m unittest discover -s tests -v
cd ..
.venv/Scripts/python tools/validate_projects.py
.venv/Scripts/python tools/validate_projects.py --headless-smoke
.venv/Scripts/python tools/check_markdown_links.py
```

## Recommended Next Step

If work resumes from this plan, the next best implementation slice is:

1. finish the command popup for the common commands used inside dialogues
2. keep the JSON fallback for uncommon command shapes
3. then decide whether to add first-class `next_dialogue_*` option fields

That order keeps momentum while avoiding a premature runtime contract change.

If the team wants to invest in the cleaner branch authoring model soon, Phase 4
is a reasonable medium-sized next feature after the current popup work.
