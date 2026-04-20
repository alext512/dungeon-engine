# Sample Content Coverage

This page explains what repo-local sample content is expected to prove for
maintainers and coding agents.

The current canonical sample project is `projects/new_project`. Treat it as a
living contract fixture: it should stay readable enough for authors to learn
from, but intentional enough to catch real engine-contract regressions.

This page is not the full authoring guide. It is the maintainer-facing checklist
for what the sample proves today and what it still does not prove.

## Current Coverage

`projects/new_project` exercises these active engine surfaces:

- manifest-driven project loading through `project.json`
- startup area selection through `startup_area`
- shared-variable display and UI defaults through `shared_variables.json`
- path-derived area, entity-template, command, dialogue, and asset ids
- title-screen dialogue data through `dialogues/system/title_menu.json`
- runtime-control commands: `new_game`, `load_game`, and `quit_game`
- project commands through `commands/player/move_one_tile.json`
- per-entity input routing through the player `input_map`
- entity command dispatch for movement, interaction, and inventory
- inventory session opening through `open_inventory_session`
- item-definition loading, pickup, and item use through
  `items/consumables/glimmer_berry.json` and
  `entity_templates/inventory_pickup.json`
- persistent restoration of the sample pickup/item-use result through
  `tests/test_sample_project_workflows.py`
- authored camera defaults in `areas/start.json` plus transition camera follow
  in `dialogues/system/title_menu.json`
- project-level global entity state through
  `project.json` `global_entities.sample_global_tracker`
- caller-supplied dialogue segment hooks through
  `entity_templates/dialogue_hook_terminal.json` and
  `dialogues/system/sample_hook_choice.json`
- inline dialogue-definition authoring through
  `entity_templates/actively_used/sign_v2.json`
- entity-owned named dialogue variants plus active-dialogue switching through
  `entity_templates/actively_used/sign_cycle.json` and
  `dialogues/signs/cycle_intro.json`
- area transitions through `change_area` and `area_transition` templates
- transferred entity ids through `transfer_entity_ids`
- entity templates with typed parameter specs, visuals, render order,
  collision, pushing, interaction, and occupancy hooks
- GID tile layers, multiple tilesets, and authored cell/entity placement
- project assets and bitmap font assets loaded through manifest asset roots

## Primary Files

Use these files as the first examples when checking sample behavior:

- `projects/new_project/project.json` for manifest paths, startup area, input
  targets, title-screen state, global entities, and runtime UI defaults
- `projects/new_project/dialogues/system/title_menu.json` for dialogue/menu data
  plus runtime-control and transition camera-follow commands
- `projects/new_project/dialogues/system/sample_hook_choice.json` and
  `projects/new_project/entity_templates/dialogue_hook_terminal.json` for the
  sample segment-hook override workflow
- `projects/new_project/entity_templates/actively_used/sign_v2.json` for an
  inline `dialogue_definition` example with nested child dialogue branches
- `projects/new_project/entity_templates/actively_used/sign_cycle.json` and
  `projects/new_project/dialogues/signs/cycle_intro.json` for an entity-owned
  `dialogues` map, `active_dialogue` selection, file-backed plus inline
  variants, and post-interaction dialogue switching
- `projects/new_project/commands/player/move_one_tile.json` for reusable project
  command loading and command composition
- `projects/new_project/entity_templates/player.json` for player input,
  inventory session opening, persistence defaults, collision, movement, and
  rendering
- `projects/new_project/items/consumables/glimmer_berry.json` and
  `projects/new_project/entity_templates/inventory_pickup.json` for the sample
  item pickup/use workflow
- `projects/new_project/entity_templates/area_transition.json` and
  `projects/new_project/entity_templates/area_transition_target.json` for
  player-gated area-change handoff behavior, traveler transfer, and transition
  camera follow
- `projects/new_project/areas/start.json` and
  `projects/new_project/areas/levels/first_area.json` for tile layers,
  template-backed entities, camera defaults, transitions, and puzzle objects

## Verification Coverage

The project is checked by:

- `tools/validate_projects.py`, which validates repo-local manifests through the
  startup validation path and can also run optional headless startup smoke
  through `--headless-smoke`
- `tests/test_startup_smoke.py`, which runs `projects/new_project` headlessly
  for two frames when that fixture is present
- runtime tests that use repo-local fixtures opportunistically when available
- `tests/test_sample_project_workflows.py`, which executes the sample item
  pickup/use path, segment-hook override, global-entity mutation, camera-default
  assertions, and save-data roundtrip to a freshly loaded area

When this sample changes, prefer validating through the same paths the runtime
uses:

```text
.venv/Scripts/python tools/validate_projects.py
.venv/Scripts/python tools/validate_projects.py --headless-smoke
.venv/Scripts/python run_game.py --project projects/new_project --headless --max-frames 2
```

For engine-contract changes, also run the focused or full runtime test suite.

## Known Gaps

No current high-value authored workflow gap is tracked on this page. Add future
gaps here when a missing sample would catch real content-facing regressions or
teach an important authoring pattern.

## Expansion Rule

Add sample coverage when the sample proves a meaningful authored workflow, not
just because a command exists. The best additions are small, visible, and tied
to a validation path.

When adding sample coverage:

- update the sample content
- update this page's coverage and gap lists
- update or add validation tests where the behavior is meant to protect the
  engine contract
- keep the author-facing docs aligned if the change teaches a new authoring
  pattern

## Maintenance Rule

When a sample project starts proving a contract, keep its docs, validation, and
tests aligned. Sample content should remain understandable enough for authors
to learn from while still catching real contract regressions.
