# Runtime Tokens

Runtime tokens let commands read data at execution time.

## String Forms

- `$token`
- `${token}`

Special numeric helper:

- `$half:token`

## Current Token Families

- `$self_id`
- `$refs.<name>...`
- `$ref_ids.<name>`
- `$project...`
- `$area...`
- `$camera...`
- `$current_area...`
- `$self...`
- `$<runtime_param>`

## What They Mean

- `$self_id` resolves to the source entity id for the current flow.
- `$refs.some_name.some_var` reads `variables` from one referenced entity.
- `$ref_ids.some_name` resolves the raw id of one referenced entity.
- `$project.foo.bar` reads from `shared_variables.json`.
- `$area.tile_size` and similar tokens read current area state.
- `$camera.x` and related tokens read camera state.
- `$current_area.some_var` reads the live current-area variable store.
- `$self.some_var` reads variables from the source entity.
- `$some_named_param` reads a runtime parameter passed into the current flow.

## Important Limitation

`$self...` and `$refs.<name>...` read entity variables, not arbitrary built-in entity fields. If you need an entity field, use the relevant command logic or a structured query/value source.

## Current Area Token State

Current area tokens currently expose values such as:

- `area_id`
- `tile_size`
- `width`
- `height`
- `pixel_width`
- `pixel_height`
- `camera`

## Current Camera Token State

Camera tokens currently expose:

- `x`
- `y`
- `follow`
- `bounds`
- `deadzone`
- `has_bounds`
- `has_deadzone`

## Structured Value Sources

The runner also supports richer single-key value-source objects.
Unknown single-key `$...` objects fail as unknown value sources, which helps catch typos early.

Current sources include:

- `$json_file`
- `$wrapped_lines`
- `$text_window`
- `$entity_ref`
- `$area_entity_ref`
- `$cell_flags_at`
- `$entities_at`
- `$entity_at`
- `$entities_query`
- `$entity_query`
- `$inventory_item_count`
- `$inventory_has_item`
- `$collection_item`
- `$add`
- `$subtract`
- `$multiply`
- `$divide`
- `$join_text`
- `$slice_collection`
- `$wrap_index`
- `$and`
- `$or`
- `$not`
- `$boolean_not`
- `$length`
- `$random_int`
- `$random_choice`
- `$find_in_collection`
- `$any_in_collection`

## Common Practical Uses

### Load ordinary JSON data

```json
{
  "$json_file": "dialogues/system/title_menu.json"
}
```

### Wrap text for dialogue or UI

```json
{
  "$wrapped_lines": {
    "text": "Hello world",
    "max_width": 120,
    "font_id": "default"
  }
}
```

### Slice a text window

```json
{
  "$text_window": {
    "lines": "$self.lines",
    "start": 0,
    "max_lines": 3,
    "separator": "\n"
  }
}
```

### Compute arithmetic values

```json
{
  "$divide": ["$project.movement.ticks_per_tile", 2]
}
```

The arithmetic helpers are `$add`, `$subtract`, `$multiply`, and `$divide`. Use these structured value sources instead of inline math strings.

### Flip strict boolean state

```json
{
  "$boolean_not": "$self.enabled"
}
```

`$boolean_not` treats `null` or a missing value as `false`, then flips it. It
raises an error for non-boolean, non-null values.

### Store a value length

```json
{
  "$length": "$self.history"
}
```

`$length` returns `0` for `null` and otherwise expects a value with a length,
such as a list, string, or object.

## When To Reach For Value Sources

Use value sources when you need:

- computed values inside command payloads
- richer data selection than a plain token can express
- ordinary JSON file loading
- collection queries or aggregation
- UI text shaping helpers

## Exact Reference

For the exhaustive current token heads, query shapes, and return shapes, see:

- [Engine JSON Interface](../manuals/engine-json-interface.md)
