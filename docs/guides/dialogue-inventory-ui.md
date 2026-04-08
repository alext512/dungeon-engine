# Dialogue, Inventory, and UI

The engine supports both high-level built-in sessions and lower-level screen-space primitives.

## Engine-Owned Dialogue Sessions

The recommended default for most dialogue and menu flows is:

- `open_dialogue_session`
- `close_dialogue_session`

The engine-owned dialogue runtime currently handles:

- text pagination
- choice selection and scrolling
- modal input ownership while active
- nested dialogue suspension and resume
- segment hooks and caller hooks
- UI preset-driven layout from `shared_variables.dialogue_ui`

This path is usually better than rebuilding dialogue from scratch.

## When To Use Inline Dialogue Commands

Inline option `commands` are a good fit when:

- the option performs a simple direct action
- you want menu options like `new_game`, `load_game`, or `quit_game`
- the behavior belongs tightly to that one option

Use `dialogue_on_end` or other caller hooks when:

- you need shared cleanup
- several outcomes should converge after the dialogue closes
- you want the calling flow to own the post-close behavior

## Controller-Owned Dialogue Still Exists

Advanced projects can still build dialogue manually using:

- input-route pushing and popping
- screen image and text commands
- entity-owned state
- project command logic

That path is more flexible, but it also means owning more boilerplate yourself.

## Inventory Is First-Class

Inventory support includes:

- item definition files discovered through `item_paths`
- entity-owned stack inventories
- commands for adding, removing, using, and resizing inventory
- an engine-owned inventory session UI

Key commands:

- `add_inventory_item`
- `remove_inventory_item`
- `use_inventory_item`
- `set_inventory_max_stacks`
- `open_inventory_session`
- `close_inventory_session`

## Item Use Flow

Items can carry authored `use_commands`, which makes them a natural place for:

- consumables
- keys or puzzle items
- utility actions
- menu-triggered effects

`use_inventory_item` only consumes the item after its use flow finishes cleanly, which is important for gameplay safety.

## Screen-Space UI Primitives

If you need custom UI behavior outside the engine-owned sessions, the runtime exposes screen-space commands such as:

- `show_screen_image`
- `show_screen_text`
- `set_screen_text`
- `remove_screen_element`
- `clear_screen_elements`
- `play_screen_animation`
- `wait_for_screen_animation`

These are useful for:

- title screens
- overlays
- custom menus
- transition panels
- UI flourishes layered on top of gameplay

## UI Presets And Shared Variables

The project-wide `shared_variables.json` surface is the right home for reusable UI configuration such as:

- dialogue layout presets
- inventory UI presets
- project-level display settings
- shared tunable values that should not live on one area or one entity

## Recommended Default Strategy

- Use engine-owned dialogue sessions for most dialogue and menus.
- Use engine-owned inventory sessions for standard inventory browsing.
- Use raw screen-space commands when you need a custom overlay or one-off presentation effect.
- Use controller-owned flows only when you genuinely need custom control.

## Deeper References

- [ENGINE_JSON_INTERFACE.md](https://github.com/alext512/dungeon-engine/blob/main/ENGINE_JSON_INTERFACE.md)
- [AUTHORING_GUIDE.md](https://github.com/alext512/dungeon-engine/blob/main/AUTHORING_GUIDE.md)
- [architecture.md](https://github.com/alext512/dungeon-engine/blob/main/architecture.md)
