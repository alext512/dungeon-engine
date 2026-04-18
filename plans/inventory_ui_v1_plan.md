# Inventory UI V1 Plan

This document captures the current agreed direction for the first inventory UI
layer.

It is a planning document, not the canonical implementation reference.
The active docs should only be updated after the implementation changes are
real.

This document is intentionally focused on:

- how the player opens and closes inventory
- how inventory browsing should feel
- the visual relationship between inventory UI and dialogue UI
- item list, description, portrait, and action popup behavior
- the boundary between engine-owned runtime behavior and authored JSON

It is not trying to solve:

- a fully generic list/menu runtime for every future system
- discard, drop-to-floor, or throw actions
- targeted or cancellable item-use sessions
- a permanent on-screen status log
- later party/combat UI

This plan builds on [inventory_v1_plan.md](inventory_v1_plan.md).

## Why This Change Exists

Inventory V1 now exists as gameplay/data functionality, but it still lacks the
main player-facing interaction layer.

Without inventory UI, the current engine can already support:

- pickups
- NPC gifts
- item-gated doors
- direct item-use commands wired manually

But the player still needs a clear, standard way to:

- inspect items
- read item descriptions
- see item counts
- choose when to use directly usable items

The goal of Inventory UI V1 is not to solve every future menu type.
It is to add one clear, practical, dialogue-adjacent inventory interface that
fits the current puzzle/story phase of the engine.

## Core Direction

The engine should own the generic runtime behavior of the inventory session.

Projects should own:

- item content
- item descriptions
- item icons and portraits
- inventory UI presets
- pause-menu presentation
- gameplay outcomes of item use

Important direction:

- inventory UI should be treated as its own engine-owned session/runtime
- it should share visual language with dialogue
- it should not be forced into literal dialogue-file authoring

So the intended relationship is:

- dialogue session and inventory session are siblings
- they may share layout ideas and panel assets
- they should not be the same authored data model

## Scope Of Inventory UI V1

Inventory UI V1 should solve:

- direct inventory opening
- discoverability through a pause menu
- list browsing
- description display
- optional icon display
- optional portrait display
- simple `Use / Cancel` action popup for usable items

Inventory UI V1 should not yet solve:

- discard
- drop to floor
- throw
- sort/filter menus
- stack splitting
- item targeting flows
- multi-step use workflows

## Access And Discoverability

### Direct Inventory Open

The player should have a dedicated logical action for inventory:

- `inventory`

Recommended default keyboard shortcut:

- `I`

This should open inventory directly without routing through the pause menu.

### Pause Menu

The pause menu should be opened by:

- `Esc`

The pause menu should be a simple dialogue-style choice menu for now.

Recommended V1 options:

- `Resume`
- `Inventory (I)`
- `Load`
- `Exit`

Close behavior:

- pressing `Esc` opens the pause menu when it is closed
- pressing `Esc` again closes the pause menu
- the explicit `Resume` option should also close it

Why both direct access and pause-menu access are useful:

- `I` is fast once the player knows it
- `Esc` makes inventory discoverable for players who do not know the shortcut

## Inventory Session Runtime

The engine should own the generic inventory session state.

That includes:

- whether inventory is open
- selected stack index
- list scroll window
- whether the action popup is open
- selected action index inside the popup
- confirm/cancel behavior
- modal input capture and restore

The engine should not own:

- item meaning
- item use success/failure flavor text
- game-specific menu actions beyond the small V1 action popup

## Visual Structure

Inventory UI V1 should be intentionally simple.

Recommended layout:

1. a main item-list panel
2. a bottom detail panel
3. a small `Use / Cancel` popup near the selected item or list area

The detail panel should show:

- item name
- quantity when greater than `1`
- optional item portrait
- item description

The list rows should show:

- optional small icon
- item name
- quantity on the right when greater than `1`

This should feel visually close to dialogue, but it does not need to be a
literal dialogue panel clone.

## Preset Direction

Inventory UI should have its own preset family, rather than reusing
`dialogue_ui.presets` as-is.

Recommended shared-variable direction:

- `inventory_ui.default_preset`
- `inventory_ui.presets`

Recommended storage location for V1:

- `shared_variables.json`

Reason:

- inventory needs list-specific and popup-specific layout information
- dialogue presets currently describe text, portrait, and choices, but not
  inventory rows or item-detail behavior

However, the inventory detail panel should intentionally mirror dialogue layout
concepts where possible.

That means an inventory preset should likely reuse similar sub-structure ideas
for:

- `panel`
- `portrait_slot`
- `text`
- `font_id`
- `text_color`
- layers

This allows a project to:

- use the same panel asset for dialogue and inventory if desired
- keep typography and positioning conventions aligned
- still have separate inventory-specific layout controls

So the preferred direction is:

- sibling preset systems
- not one identical preset schema
- but with overlapping structure where it makes sense

## Engine Defaults And Sparse Presets

Inventory UI V1 should have engine-owned fallback defaults.

This does not mean the engine owns the project's final visual style.
It means:

- the engine provides one usable full fallback layout
- project presets may override only the fields they care about
- missing preset fields are filled from engine defaults

Why this is the preferred V1 direction:

- lowers the authoring floor
- avoids forcing projects to write a huge preset blob immediately
- matches the practical fallback style already used by the dialogue runtime

So the intended model is:

- engine default inventory layout
- sparse project preset overrides
- merged result at runtime

This also means the larger representative preset shown below is the target
shape, not the minimum required authoring burden for V1.

## Suggested Inventory Preset Shape

Representative direction:

```json
{
  "inventory_ui": {
    "default_preset": "standard",
    "presets": {
      "standard": {
        "list_panel": {
          "path": "assets/project/ui/dialogue_panel.png",
          "x": 0,
          "y": 40
        },
        "list": {
          "x": 8,
          "y": 48,
          "width": 150,
          "visible_rows": 8,
          "row_height": 10,
          "icon_size": 16,
          "quantity_align": "right"
        },
        "detail_panel": {
          "path": "assets/project/ui/dialogue_panel.png",
          "x": 0,
          "y": 148
        },
        "portrait_slot": {
          "x": 3,
          "y": 151,
          "width": 38,
          "height": 38
        },
        "text": {
          "plain": {
            "x": 8,
            "y": 154,
            "width": 240,
            "max_lines": 3
          },
          "with_portrait": {
            "x": 56,
            "y": 154,
            "width": 192,
            "max_lines": 3
          }
        },
        "action_popup": {
          "panel": {
            "path": "assets/project/ui/dialogue_panel.png",
            "x": 168,
            "y": 120
          },
          "x": 176,
          "y": 128,
          "width": 56,
          "row_height": 10
        },
        "font_id": "pixelbet",
        "text_color": [245, 232, 190],
        "choice_text_color": [238, 242, 248],
        "ui_layer": 100,
        "text_layer": 101
      }
    }
  }
}
```

The exact schema can still evolve during implementation, but the intended
shape is:

- list section
- detail section
- popup section
- dialogue-like detail text and portrait substructure

## Item Presentation Fields

Current item definitions already support:

- `name`
- `description`
- `icon`
- `max_stack`
- `consume_quantity_on_use`
- `use_commands`

Recommended Inventory UI addition:

- optional item `portrait`

Representative shape:

```json
{
  "name": "Light Orb",
  "description": "Feeds the nearby beacon terminal once.",
  "icon": {
    "path": "assets/project/items/light_orb_icon.png",
    "frame_width": 16,
    "frame_height": 16,
    "frame": 0
  },
  "portrait": {
    "path": "assets/project/items/light_orb_portrait.png",
    "frame_width": 38,
    "frame_height": 38,
    "frame": 0
  },
  "max_stack": 3,
  "consume_quantity_on_use": 1,
  "use_commands": []
}
```

Recommended meaning:

- `icon` is for the list row
- `portrait` is for the bottom detail panel

Why this is useful:

- icons improve quick scanning
- portraits make the detail area feel richer
- projects can omit either or both

## Usability Rule

Inventory UI V1 should not add a separate item field such as `usable`.

Usability should be derived from the item definition:

- if `use_commands` exists and is non-empty, the item is directly usable
- otherwise, it is not directly usable from the inventory UI

This avoids redundant data and avoids mismatches like:

- `usable: true` but no `use_commands`

## Browsing Behavior

Inventory browsing should be modal while open.

Recommended controls:

- movement inputs navigate the list
- `interact` acts as confirm/select
- `menu` or `Esc` acts as back/cancel

List behavior:

- rows should scroll when selection moves beyond the visible window
- the selected row controls the detail panel content
- non-usable items should remain fully browsable

Scrolling should be selection-snapped, not smooth-scrolling.

That means:

- the cursor moves one row at a time
- when the selection would leave the visible window, the visible window shifts
  immediately
- there is no inertial or pixel-smooth list motion in V1

The detail panel should always remain useful even for non-usable items because
it still shows:

- item art
- description
- quantity

## Item Action Popup

When the selected item is directly usable:

- pressing `interact` should open a small `Use / Cancel` popup

When the selected item is not directly usable:

- no popup should open

This popup is intentionally small and future-friendly.
Even if V1 only uses:

- `Use`
- `Cancel`

the popup shape leaves room later for:

- `Discard`
- `Drop`
- `Info`

without redesigning the entire interaction model.

## Unusable Item Feedback

For items with no `use_commands`, pressing `interact` should not silently do
nothing.

Recommended V1 behavior:

- play a small deny/error sound
- keep the inventory open
- do not open the action popup

Optional later polish:

- briefly replace or overlay the description text with a tiny inline notice
  such as `Can't use`

But that inline notice is not required for the first pass.

The important V1 rule is:

- give lightweight feedback
- do not open a pointless `Cancel`-only popup

## Empty Inventory Behavior

Opening inventory with no items should still work.

Recommended V1 behavior:

- inventory opens normally
- the list shows an empty-state message such as `No items`
- the detail panel shows a simple empty-state line such as `Inventory empty.`
- there is no active item selection
- the action popup cannot open
- pressing `interact` does nothing or plays the same tiny deny sound

Inventory should not refuse to open just because it is empty.
That would be confusing and would make the feature feel hidden or broken.

## Item Use Flow

Recommended V1 flow:

1. player opens inventory
2. player highlights an item
3. player presses `interact`
4. if the item is usable, the `Use / Cancel` popup opens
5. if the player chooses `Use`, the inventory closes immediately
6. the engine runs the normal `use_inventory_item` flow

Why close first:

- returns control to the world cleanly
- avoids awkward modal-over-modal situations
- fits puzzle/story item use better than leaving the inventory open

Important V1 rule:

- once `Use` is chosen, inventory closes even if later authored conditions mean
  the item does not have a meaningful effect in the current context

That later feedback should come from normal authored content, not from the
inventory UI itself.

## Item Use Feedback

Inventory UI V1 should stay lightweight.

It should not try to own rich item-use messaging.

Recommended V1 direction:

- inventory closes on confirmed `Use`
- the item's normal `use_commands` handle any meaningful success/failure
  feedback
- feedback may be done through:
  - dialogue
  - world changes
  - sounds
  - future status-log integration later

Examples:

- key use that opens a door
- item use that opens a small dialogue like `No door here.`
- item use that toggles a terminal or beacon

This keeps the inventory UI generic and avoids baking puzzle semantics into the
menu layer.

## Status Log Direction

A permanent on-screen PMD-style status log should not be part of Inventory UI
V1.

Reason:

- it takes persistent screen space
- current puzzle/story gameplay does not yet prove that constant message-feed
  occupancy is worth it
- lightweight feedback is enough for this phase

Later, if broader gameplay justifies it, a message log can still be added as a
separate sibling system.

But Inventory UI V1 should not block on that.

## Pause Menu Runtime Direction

The pause menu does not need its own separate session type in V1.

Recommended direction:

- implement the pause menu as a normal dialogue-style choice session

Why this is acceptable:

- the pause menu is static
- the option list is small
- it does not need inventory-style runtime data browsing

This does not conflict with the decision that inventory should not be forced
into dialogue-style content authoring, because inventory is fundamentally a
dynamic data-driven list while the pause menu is a small fixed choice prompt.

## Save/Load Note

The suggested pause menu includes `Load` but not `Save`.

That is intentional for the current direction.

The current preference is to keep saving tied to explicit authored save points
rather than exposing a universal global save action in the pause menu.

Later, if needed, projects may still gain a setting or policy for broader save
availability, but Inventory UI V1 should not assume that.

## Item Actions Explicitly Deferred

These actions should not be part of Inventory UI V1:

- discard/delete
- place on floor
- throw
- give to another entity
- split stack

Why they are deferred:

- discard would likely need item-level policy such as `deletable`
- place-on-floor needs clear world/drop semantics
- throw is a larger targeting/system feature

Inventory UI V1 should stay focused on:

- browse
- inspect
- use
- cancel

## Editor Boundary

Manual JSON authoring for item behavior still makes sense.

The likely healthy long-term split is:

- editor-friendly item fields for:
  - name
  - description
  - icon
  - portrait
  - `max_stack`
  - `consume_quantity_on_use`
- manual JSON authoring for:
  - `use_commands`
  - more conditional/custom item behavior

This fits the current engine well because:

- item behavior can already be expressive
- simple metadata should still become easier to edit later
- advanced use flows should not be oversimplified artificially

## Future Generic Menu Relationship

This plan deliberately does not try to fully solve the larger future generic
list/menu session problem.

Current preferred direction:

- implement inventory UI first as the concrete next step
- keep the runtime reasonably reusable internally
- only later decide how much of that should be generalized into a wider
  list/menu session family

This avoids prematurely over-abstracting inventory into a generic API before
real usage proves what should actually be shared.

## Known V1 Friction

Inventory UI V1 intentionally accepts one small usability tradeoff:

- after a successful `Use`, the inventory closes
- using multiple consumables in a row therefore requires reopening inventory

This is acceptable for the current puzzle/story-oriented phase because the main
goal is clean modal behavior, not rapid repeated combat-item usage.

If later gameplay proves repeated chained item use is common, that can become a
future refinement.

## Recommended Implementation Order

1. Add item `portrait` support to item definitions
2. Add shared-variable support for `inventory_ui` presets
3. Implement the inventory session runtime:
   - open/close
   - selection
   - scroll window
   - action popup state
4. Add direct `inventory` input routing and opening behavior
5. Add a simple pause menu with:
   - `Resume`
   - `Inventory (I)`
   - `Load`
   - `Exit`
6. Render the inventory list panel, detail panel, and popup
7. Wire `Use / Cancel` behavior into `use_inventory_item`
8. Add lightweight non-usable feedback
9. Expand the canonical demo project to show:
   - direct-use item
   - non-usable quest/key item
   - portrait-bearing item
   - pause-menu discoverability

## Bottom Line

Inventory UI V1 should be:

- simple
- readable
- dialogue-adjacent in visual language
- inventory-specific in runtime behavior
- explicit about what it does not solve yet

That is enough to make the new inventory system truly usable without dragging
the engine into a premature full-menu framework or a combat-oriented UI stack.
