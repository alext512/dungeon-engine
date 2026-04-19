# Startup Checks

Use this page when you want to know what the engine checks before play begins, or when an authored project fails during startup.

## What Startup Validation Currently Checks

`run_game.py` calls the startup validator before play begins.

The current order is:

1. entity template validation
2. item-definition validation
3. area validation
4. project-command validation
5. strict command-authoring audit
6. static reference validation

That means many authored mistakes fail before the main loop starts.

## What The Command-Authoring Audit Scans

The strict command-authoring pass currently audits known command-bearing JSON surfaces such as:

- project command files under `command_paths`
- item `use_commands`
- template `entity_commands`
- area `enter_commands`
- inline area-entity `entity_commands`
- `project.json` `global_entities[*].entity_commands`
- dialogue JSON under the conventional `dialogues/` tree
- nested deferred command payloads such as inline `dialogue_definition`,
  `segment_hooks`, inline option commands, option-level
  `next_dialogue_definition`, and `option_commands_by_id`

One practical benefit is that likely top-level typos on strict primitive commands, such as `persitent` instead of `persistent`, fail before launch.

## What Static Reference Validation Catches

The static-reference pass currently checks statically resolvable dialogue and asset references across:

- `project.json`
- `shared_variables.json`
- JSON files under configured template, area, command, item, and asset roots
- dialogue JSON under the conventional `project_root/dialogues/` tree
- loaded areas and loaded global entities after template expansion

This catches issues such as:

- missing literal `dialogue_path` values
- missing literal `next_dialogue_path` values
- missing literal asset paths
- missing literal asset/dialogue references that only become visible after template parameters are applied

## What It Intentionally Does Not Treat As Broken Up Front

Dynamic runtime references are not rejected just because they are dynamic.

Examples:

- token-based values such as `$sprite_path`
- other runtime-filled references that cannot be resolved safely at startup

So the startup validator is strong, but it is not a substitute for real gameplay coverage.

## Important Convention: `dialogues/`

Dialogue and menu JSON is ordinary project-relative JSON and can be loaded through `$json_file`.

However, the current extra startup dialogue scanning is still convention-based: it walks the conventional `dialogues/` folder specifically. Keeping dialogue/menu data there gives you the most tooling and validation coverage today.

## What Authors Should Take From This

- Literal asset and dialogue references are checked earlier than dynamic token-filled ones.
- Keeping dialogue and menu JSON under `dialogues/` gives you the most validation coverage today.
- If you rename files or command ids, a quick relaunch often catches mistakes immediately.
- Dynamic references still need real gameplay coverage because they may only resolve at runtime.

## Quick Startup Smoke

If you want a fast project-load check without playing through the full game loop:

```text
.venv/Scripts/python run_game.py --project projects/new_project --headless --max-frames 2
```

## If You Are Maintaining The Engine

Use [Verification and Validation](../development/verification-and-validation.md) for runtime tests, editor tests, repo-wide validation workflow, and docs-build commands.
