# Content Types

This engine is easiest to use when you think in content types rather than in loose JSON blobs.

## Project-Wide Shared Data

### `shared_variables.json`

This is an ordinary JSON object loaded once at project startup.

Common current uses:

- display dimensions
- dialogue UI presets
- inventory UI presets
- shared values that multiple systems need

Runtime tokens can read it through `$project...`.

## Items

Item files are discovered through `item_paths`.

Current item fields include:

- `name`
- `description`
- `icon`
- `portrait`
- `max_stack`
- `consume_quantity_on_use`
- `use_commands`

Use item files for:

- consumables
- keys
- reusable usable objects
- inventory-driven puzzle behavior

## Areas

Area files are the main room-level content surface.

Current area fields include:

- `tile_size`
- `variables`
- `tilesets`
- `tile_layers`
- `cell_flags`
- `enter_commands`
- `entry_points`
- `camera`
- `input_targets`
- `entities`

Areas define:

- room layout
- room-local entities
- room-local startup behavior
- local runtime variables
- room camera defaults

## Entity Templates And Instances

Templates define reusable entity shapes. Instances place them into areas or into `project.json` globals.

Common engine-known entity fields include:

- identity and placement such as `id`, `grid_x`, `grid_y`, `pixel_x`, `pixel_y`
- physics and interaction fields such as `facing`, `solid`, `pushable`, `interactable`
- rendering fields such as `render_order`, `y_sort`, `sort_y_offset`, `stack_order`
- authored state such as `variables`, `inventory`, `visuals`, `entity_commands`, `input_map`
- persistence policy through `persistence`

Template parameter substitution happens before runtime command execution and is different from runtime tokens.

## Project Commands

Project command files are reusable command-chain definitions discovered through `command_paths`.

Current file shape:

- `params`
- `deferred_param_shapes`
- `commands`

Use project commands when logic is:

- reused in multiple places
- not naturally owned by one single entity
- easier to maintain as a project-wide behavior unit

## Ordinary Project JSON Data

Not every content file needs a manifest category.

Any ordinary JSON file under the project root can be loaded through the `$json_file` value source. This is why dialogue data often lives under `dialogues/` without needing a dedicated manifest field.

That said, `dialogues/` is more than just a style preference right now. Dialogue and menu data conventionally lives there, editor dialogue pickers use that convention, and startup command/static-reference auditing also scans that tree specifically.

## Path-Derived IDs

Typed content gets ids from its file path under the configured root.

Examples:

- `areas/start.json` -> `areas/start`
- `entity_templates/player.json` -> `entity_templates/player`
- `commands/dialogue/open.json` -> `commands/dialogue/open`

That convention is one of the reasons reference-aware rename or move support matters in the editor.

## Exact Current Contract

For the exhaustive shape of these content types, use:

- [Engine JSON Interface](../manuals/engine-json-interface.md)
- [Authoring Guide](../manuals/authoring-guide.md)
