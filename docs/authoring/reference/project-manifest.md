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
- `command_runtime: object`

## Defaults And Fallbacks

- If a path array is omitted or empty, the engine falls back to a conventional folder under the project root.
- `shared_variables_path` falls back to `shared_variables.json` if present.
- `save_dir` defaults to `saves`.
- `command_runtime` is optional; omitted fields use engine defaults.

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
  "debug_inspection_enabled": true,
  "command_runtime": {
    "max_settle_passes": 128,
    "max_immediate_commands_per_settle": 8192,
    "log_settle_usage_peaks": false,
    "settle_warning_ratio": 0.75
  }
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

### `command_runtime`

Optional command-runner safety and diagnostics settings.

Current fields:

- `max_settle_passes`
  Maximum game-command settle passes before the runner treats the current
  command cascade as an error.
- `max_immediate_commands_per_settle`
  Maximum immediate command executions allowed during one settle before the
  runner treats the cascade as an error.
- `log_settle_usage_peaks`
  When `true`, logs the largest settle workload seen so far during the run.
- `settle_warning_ratio`
  Emits a warning when a settle reaches this fraction of either safety limit.

These are safety fuses, not frame budgets. If the limit is reached, the engine
does not quietly continue the rest of the ready work next tick; it logs a
command error so the authored cascade can be fixed.

## Practical Advice

- Keep the manifest small and declarative.
- Put project-wide settings here, not per-room behavior.
- Prefer path-root organization that stays stable over time, since renames affect ids.
- If you add or rename command-bearing content, validate the actual project manifests directly.

## Deep Reference

For the exact current manifest contract and notes, see:

- [Engine JSON Interface](../manuals/engine-json-interface.md)
