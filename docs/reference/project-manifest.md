# Project Manifest

The runtime starts from `project.json`. This file tells the engine where to find project content and how to initialize project-level behavior.

## Current Manifest Fields

- `entity_template_paths: string[]`
- `asset_paths: string[]`
- `area_paths: string[]`
- `command_paths: string[]`
- `item_paths: string[]`
- `shared_variables_path: string`
- `save_dir: string`
- `global_entities: object[]`
- `startup_area: string`
- `input_targets: object`
- `debug_inspection_enabled: boolean`

## Defaults And Fallbacks

- If a path array is omitted or empty, the engine falls back to a conventional folder under the project root.
- `shared_variables_path` falls back to `shared_variables.json` if present.
- `save_dir` defaults to `saves`.

## Example

```json
{
  "entity_template_paths": ["entity_templates/"],
  "asset_paths": ["assets/"],
  "area_paths": ["areas/"],
  "command_paths": ["commands/"],
  "item_paths": ["items/"],
  "shared_variables_path": "shared_variables.json",
  "global_entities": [
    { "id": "dialogue_controller", "template": "entity_templates/dialogue_panel" }
  ],
  "startup_area": "areas/title_screen",
  "input_targets": {
    "menu": "pause_controller"
  },
  "debug_inspection_enabled": true
}
```

## What Each Field Really Means

### Content roots

These tell the engine how to discover typed content:

- `entity_template_paths`
- `asset_paths`
- `area_paths`
- `command_paths`
- `item_paths`

Because ids are path-derived, these roots affect how references are resolved.

### `shared_variables_path`

Points to the project-wide JSON object that currently powers things like:

- display size
- dialogue UI presets
- inventory UI presets
- shared tunable values

### `global_entities`

Global entities use the same instance shape as area entities, but they are project-level runtime entities. They are injected into active play worlds and persist independently from per-area authored content.

### `startup_area`

This is the default area loaded when you run the project unless you explicitly pass another area id on the CLI.

### `input_targets`

This is the project-level logical-action routing table. Area `input_targets` can layer on top of it.

### `debug_inspection_enabled`

Enables debug runtime features such as pausing simulation, stepping ticks, and output-scale adjustments.

## Practical Advice

- Keep the manifest small and declarative.
- Put project-wide settings here, not per-room behavior.
- Prefer path-root organization that stays stable over time, since renames affect ids.
- If you add or rename command-bearing content, validate the actual project manifests directly.

## Deep Reference

For the exact current manifest contract and notes, see:

- [ENGINE_JSON_INTERFACE.md](https://github.com/alext512/dungeon-engine/blob/main/ENGINE_JSON_INTERFACE.md)
