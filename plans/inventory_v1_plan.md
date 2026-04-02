# Inventory V1 Plan

This document captures the current agreed direction for the first inventory
system.

It is a planning document, not the canonical implementation reference.
The active docs should only be updated after the implementation changes are
real.

This document is intentionally focused on:

- item definitions
- entity-owned inventory data
- stack and capacity rules
- item use
- result reporting
- pickup authoring patterns
- the boundary between engine-owned behavior and authored JSON

It is not trying to solve:

- inventory UI
- equipment systems
- party/member item targeting
- combat-oriented resources
- advanced container/shop UX

## Why This Change Exists

The engine already supports story and puzzle gameplay well, but it is still
missing a basic reusable inventory contract.

Inventory meaningfully expands the design space for:

- keys
- quest items
- consumables
- reusable tools
- puzzle state carried across rooms
- item-gated interactions and conditions

The goal of Inventory V1 is not to build a full RPG item framework.
It is to add one clear, flexible, engine-owned inventory contract that authored
JSON can build on.

## Design Rules

- The engine owns generic inventory semantics.
- JSON owns item content, item effects, pickup behavior, and project-specific
  logic.
- Inventories are entity-owned, not hardcoded as player-only.
- Item definitions are ordinary project JSON content.
- Path-derived ids should be used for item identity, just like commands and
  templates.
- Inventory UI is deferred; the data model should not be distorted to fit a UI
  that does not exist yet.
- Pickup behavior should stay template-driven for V1, not hardcoded as a
  special engine entity type.
- Low-level JSON command power remains available as an escape hatch.

## Project Manifest Direction

Projects should gain a new manifest field:

- `item_paths`

Recommended shape:

```json
{
  "entity_template_paths": ["entity_templates/"],
  "asset_paths": ["assets/"],
  "area_paths": ["areas/"],
  "command_paths": ["commands/"],
  "item_paths": ["items/"],
  "shared_variables_path": "shared_variables.json"
}
```

Items should use path-derived ids, for example:

- `items/apple`
- `items/copper_key`
- `items/orb_of_light`

## Item Definition Contract

Items should be ordinary JSON files under the configured item roots.

Recommended V1 shape:

```json
{
  "name": "Apple",
  "description": "A simple snack.",
  "icon": {
    "path": "assets/project/items/apple.png",
    "frame_width": 16,
    "frame_height": 16,
    "frame": 0
  },
  "max_stack": 9,
  "consume_quantity_on_use": 1,
  "use_commands": [
    {
      "type": "append_message_log_entry",
      "text": "You ate the apple."
    }
  ]
}
```

Supported V1 concepts:

- `name`
- optional `description`
- optional `icon`
- `max_stack`
- `consume_quantity_on_use`
- optional `use_commands`

Recommended defaults:

- `max_stack = 1`
- `consume_quantity_on_use = 0`
- `use_commands = []`

Clarifications:

- `max_stack = 1` means the item is effectively non-stackable.
- Items without `use_commands` are valid.
- Items with `consume_quantity_on_use = 0` may still be removed explicitly by
  authored commands if desired.

## Entity Inventory Contract

Inventories should live on entities as a top-level engine-known field.

Recommended shape:

```json
{
  "kind": "player",
  "inventory": {
    "max_stacks": 10,
    "stacks": [
      {
        "item_id": "items/apple",
        "quantity": 3
      },
      {
        "item_id": "items/copper_key",
        "quantity": 1
      }
    ]
  }
}
```

Meaning:

- `max_stacks` is the inventory capacity
- `stacks` is the ordered list of item stacks

Clarifications:

- Inventories are entity-owned in general, even if the player is the main
  immediate use case.
- This leaves room later for chests, shops, party members, and other
  containers.
- Entities without an `inventory` field should be treated as not having a V1
  inventory unless later commands explicitly create one.

## Stack Rules

The engine should own stack behavior.

Standard V1 rules:

- `max_stack` must be at least `1`
- stack quantities may never exceed the item's `max_stack`
- existing partial stacks should be filled before opening new stacks
- if new stacks are needed, they may be created only while `max_stacks` allows
  them
- mutating add/remove commands must declare
  `quantity_mode: "atomic" | "partial"`
- stack cleanup should remove zero-quantity stacks automatically

Example:

- item `items/apple` has `max_stack = 9`
- inventory already contains one apple stack with quantity `8`
- an add operation requests `3`

Then the engine should:

- fill the existing stack from `8` to `9`
- attempt to place the remaining `2` in a new stack if there is room

## Builtin Command Direction

Recommended V1 mutating commands:

- `add_inventory_item`
- `remove_inventory_item`
- `use_inventory_item`
- `set_inventory_max_stacks`

Recommended V1 read-only helpers should prefer value sources instead of extra
command types.

### `add_inventory_item`

Purpose:

- add quantity of an item to an entity inventory

Suggested authored shape:

```json
{
  "type": "add_inventory_item",
  "entity_id": "player",
  "item_id": "items/apple",
  "quantity": 3,
  "quantity_mode": "partial",
  "result_var_name": "last_inventory_result"
}
```

Meaning:

- modify `player.inventory`
- try to add `3` apples
- `quantity_mode` is required:
  - `"atomic"` means add all requested quantity or add nothing
  - `"partial"` means add as much as fits
- if `result_var_name` is provided, write the operation result to
  `$self_id.variables.last_inventory_result`

### `remove_inventory_item`

Purpose:

- remove quantity of an item from an entity inventory

Suggested authored shape:

```json
{
  "type": "remove_inventory_item",
  "entity_id": "player",
  "item_id": "items/copper_key",
  "quantity": 1,
  "quantity_mode": "atomic",
  "result_var_name": "last_inventory_result"
}
```

Meaning:

- `quantity_mode` is required:
  - `"atomic"` means remove all requested quantity or remove nothing
  - `"partial"` means remove as much as exists up to the requested quantity

### `use_inventory_item`

Purpose:

- verify the entity has enough of the item
- load the item definition
- run the item's `use_commands`
- only if those commands finish successfully, consume
  `consume_quantity_on_use * quantity`

Suggested authored shape:

```json
{
  "type": "use_inventory_item",
  "entity_id": "player",
  "item_id": "items/orb_of_light",
  "quantity": 1,
  "result_var_name": "last_inventory_result"
}
```

### `set_inventory_max_stacks`

Purpose:

- set or change an entity's inventory capacity

Suggested authored shape:

```json
{
  "type": "set_inventory_max_stacks",
  "entity_id": "player",
  "max_stacks": 12
}
```

This is useful for:

- upgrades
- bags
- temporary limits in special modes

If a command tries to shrink capacity below the number of stacks currently in
use, it should fail unchanged.

V1 should never silently discard items when inventory capacity is reduced.

## Item Change Result Object Contract

`add_inventory_item`, `remove_inventory_item`, and `use_inventory_item` should
optionally write a result object when `result_var_name` is provided.

V1 direction:

- the result should be written on `$self_id`
- the field name should be `variables[result_var_name]`
- no separate `result_entity_id` is needed for V1

Recommended result shape:

```json
{
  "success": true,
  "item_id": "items/apple",
  "requested_quantity": 5,
  "changed_quantity": 3,
  "remaining_quantity": 2
}
```

V1 intentionally does not include a `reason` field in this result object.
Expected gameplay requirements should usually be checked explicitly before the
operation, while the result quantities describe what actually changed.

Meaning:

- `success`: whether the command resolved cleanly enough for authored logic to
  trust the result object
- `requested_quantity`: how much the command tried to change
- `changed_quantity`: how much actually changed
- `remaining_quantity`: how much could not be added, removed, or consumed

Important authoring rule:

- if authored logic cares whether inventory state actually changed, it should
  check `changed_quantity > 0`
- `success` alone is not enough for pickup or transfer-style follow-up logic

Why this is useful:

- pickup entities can decide whether to destroy themselves
- NPCs can branch between "inventory full" and "item received"
- advanced flows can partially reduce a pickup quantity instead of removing it
  entirely

Example:

```json
{
  "type": "add_inventory_item",
  "entity_id": "$ref_ids.instigator",
  "item_id": "$self.item_id",
  "quantity": "$self.quantity",
  "quantity_mode": "partial",
  "result_var_name": "last_inventory_result"
}
```

If this runs on a pickup entity, then the result is written on that pickup
entity itself as:

```json
{
  "variables": {
    "last_inventory_result": {
      "success": true,
      "item_id": "items/apple",
      "requested_quantity": 1,
      "changed_quantity": 1,
      "remaining_quantity": 0
    }
  }
}
```

## Value Sources And Conditions

Inventory conditions should prefer normal value-source reads instead of a large
family of special-purpose commands.

Recommended V1 value sources:

- `$inventory_item_count`
- `$inventory_has_item`

Suggested shapes:

```json
{
  "$inventory_item_count": {
    "entity_id": "player",
    "item_id": "items/apple"
  }
}
```

```json
{
  "$inventory_has_item": {
    "entity_id": "player",
    "item_id": "items/copper_key",
    "quantity": 1
  }
}
```

These should support cases like:

- locked doors requiring a key
- puzzles that require at least `N` of an item
- dialogue options gated by inventory state

## Item Use Execution Context

`use_inventory_item` should support immediate, fully resolved item use in V1.

It should not try to solve later advanced cases like:

- target-a-tile item use
- target-a-party-member item use
- cancellable item targeting sessions

Those can become a later higher-level item-use session system.

For V1, item use should run immediately in a normal command context.
It should behave effectively as an atomic action:

- either the use executes successfully and any configured consumption happens
- or the use fails and nothing is consumed

Recommended direction:

- the inventory-owning entity should be exposed to the item use flow as
  `instigator`
- authored commands may still use normal refs and context to interact with the
  world
- targeted item UI is explicitly deferred

This keeps V1 simple while still allowing authored patterns like:

- use key on the interacted door
- use orb to toggle an area variable
- consume food and append a message

## Pickup Authoring Pattern

V1 should not introduce a special engine-owned collectible entity type.

Instead, pickups should remain authored through reusable templates plus
inventory builtins.

Why this is the preferred V1 direction:

- pickup behavior is common but not completely uniform
- some games want auto-pickup
- some games want manual pickup
- some pickups should play sounds or open dialogue
- some pickups should remain on the ground when the inventory is full

Templates plus editor support can make this convenient without hardcoding too
much engine behavior.

### Example: Ground Pickup

Suggested pickup entity template:

```json
{
  "kind": "pickup",
  "solid": false,
  "interactable": true,
  "variables": {
    "item_id": "$item_id",
    "quantity": "$quantity"
  },
  "entity_commands": {
    "interact": {
      "commands": [
        {
          "type": "add_inventory_item",
          "entity_id": "$ref_ids.instigator",
          "item_id": "$self.item_id",
          "quantity": "$self.quantity",
          "quantity_mode": "partial",
          "result_var_name": "last_inventory_result"
        },
        {
          "type": "if",
          "left": "$self.last_inventory_result.changed_quantity",
          "op": "gt",
          "right": 0,
          "then": [
            {
              "type": "append_message_log_entry",
              "text": "Picked up an Apple."
            },
            {
              "type": "destroy_entity",
              "entity_id": "$self_id"
            }
          ],
          "else": [
            {
              "type": "append_message_log_entry",
              "text": "Inventory full."
            }
          ]
        }
      ]
    }
  }
}
```

This keeps pickup logic:

- ordinary
- reusable
- easy to template in the editor later

## Complete Example Flows

### NPC Gives The Player A Key

```json
{
  "kind": "npc",
  "solid": true,
  "interactable": true,
  "variables": {
    "gave_key": false
  },
  "entity_commands": {
    "interact": {
      "commands": [
        {
          "type": "if",
          "left": "$self.gave_key",
          "op": "eq",
          "right": false,
          "then": [
            {
              "type": "add_inventory_item",
              "entity_id": "$ref_ids.instigator",
              "item_id": "items/copper_key",
              "quantity": 1,
              "quantity_mode": "atomic",
              "result_var_name": "last_inventory_result"
            },
            {
              "type": "if",
              "left": "$self.last_inventory_result.changed_quantity",
              "op": "gt",
              "right": 0,
              "then": [
                {
                  "type": "set_entity_var",
                  "entity_id": "$self_id",
                  "name": "gave_key",
                  "value": true
                },
                {
                  "type": "open_dialogue_session",
                  "dialogue_path": "dialogues/npcs/key_given.json"
                }
              ],
              "else": [
                {
                  "type": "open_dialogue_session",
                  "dialogue_path": "dialogues/npcs/inventory_full.json"
                }
              ]
            }
          ]
        }
      ]
    }
  }
}
```

### Locked Door Requires And Consumes A Key

```json
{
  "kind": "door",
  "solid": true,
  "interactable": true,
  "variables": {
    "unlocked": false
  },
  "entity_commands": {
    "interact": {
      "commands": [
        {
          "type": "if",
          "left": {
            "$inventory_has_item": {
              "entity_id": "$ref_ids.instigator",
              "item_id": "items/copper_key",
              "quantity": 1
            }
          },
          "op": "eq",
          "right": true,
          "then": [
            {
              "type": "remove_inventory_item",
              "entity_id": "$ref_ids.instigator",
              "item_id": "items/copper_key",
              "quantity": 1,
              "quantity_mode": "atomic",
              "result_var_name": "last_inventory_result"
            },
            {
              "type": "if",
              "left": "$self.last_inventory_result.changed_quantity",
              "op": "gt",
              "right": 0,
              "then": [
                {
                  "type": "set_entity_var",
                  "entity_id": "$self_id",
                  "name": "unlocked",
                  "value": true
                },
                {
                  "type": "set_entity_field",
                  "entity_id": "$self_id",
                  "field_name": "solid",
                  "value": false
                }
              ]
            }
          ],
          "else": [
            {
              "type": "append_message_log_entry",
              "text": "The door is locked."
            }
          ]
        }
      ]
    }
  }
}
```

### Direct Item Use From Inventory

If the player later chooses `items/orb_of_light` from an inventory menu, the
runtime could invoke:

```json
{
  "type": "use_inventory_item",
  "entity_id": "player",
  "item_id": "items/orb_of_light",
  "quantity": 1,
  "result_var_name": "last_inventory_result"
}
```

The engine should then:

1. verify the player has the item
2. load the item definition
3. run the item's `use_commands`
4. consume `consume_quantity_on_use * quantity` only if those commands succeed

## Persistence

Inventory state must round-trip cleanly through saves.

That means:

- `max_stacks` must persist
- stack order must persist
- each `item_id`
- each `quantity`

Save/load should restore inventory exactly as it was, without loss,
duplication, or corruption of stack state.

If a saved stack references an item definition that no longer exists, V1 should:

- preserve the stack instead of silently deleting it
- emit a warning during load
- treat the stack as unresolved until the missing definition is restored or the
  stack is explicitly removed by authored logic

## Validation Expectations

When implemented, validation should include at least:

- missing item definition detection
- `max_stack >= 1`
- `consume_quantity_on_use >= 0`
- inventory stack quantities must be positive
- inventory stack quantities may not exceed item `max_stack`
- duplicate invalid states should be rejected or normalized consistently

Items with no `use_commands` should behave predictably.

Preferred V1 direction:

- they remain valid items
- `use_inventory_item` should fail cleanly if no meaningful use exists
- failed or unresolved use should not consume inventory quantity

## Explicitly Deferred

These are intentionally out of scope for Inventory V1:

- inventory UI runtime
- item sorting and filtering UX
- equipment systems
- item categories with built-in engine meaning
- weight/bulk encumbrance systems
- multi-container or bag hierarchies
- tile/member targeting UI for item use
- cancellable item-targeting sessions
- automatic engine-owned pickup entity types
- player preference systems such as auto-pickup toggles

Those may be valuable later, but they should not complicate the first inventory
contract.

## Recommended Implementation Order

1. Add project support for `item_paths`
2. Add item loading and validation
3. Add entity inventory data and persistence
4. Add stack-resolution helpers
5. Add `add_inventory_item`
6. Add `remove_inventory_item`
7. Add inventory value sources/conditions
8. Add `use_inventory_item`
9. Add a dedicated example project or example content slice that demonstrates:
   - pickup
   - NPC gift
   - locked-door key use
   - direct consumable use
10. Only after that, discuss inventory UI

## Bottom Line

Inventory V1 should be:

- entity-owned
- item-definition driven
- stack-based
- simple in capacity rules
- explicit in command behavior
- flexible in pickup authoring

That is enough to significantly expand puzzle RPG gameplay without prematurely
locking the engine into a full RPG/combat framework.
