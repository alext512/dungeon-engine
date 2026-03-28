# UX Notes

These are workflow notes for a future UI, not a locked interface spec.

## Main User Story

The user wants to open a room, paint tiles, place entities, and adjust important instance values without hand-editing large JSON blocks.

The tool should support that path efficiently.

## Likely Primary Workflow

1. Choose a project.
2. Choose an area.
3. View the area with visible layers and entities.
4. Paint tiles on the active layer.
5. Toggle cell flags such as walkability.
6. Place or move entities.
7. Select an entity and edit key values.
8. Save.
9. Optionally launch the runtime to test.

## Important Interaction Priorities

The future UI should make these especially easy:

- switching layers
- picking a tileset and tile frame
- seeing the current cell coordinates
- seeing the entity stack on a cell
- assigning unique entity ids
- editing parameters that reference another entity in the room

## Entity Reference Editing

This is one of the highest-value features.

If a parameter is known or suspected to reference another entity:

- show a room-local picker instead of a plain free-text box
- display both entity id and a little context such as template or position
- allow clearing the reference explicitly
- surface broken references clearly

Potential later filters:

- filter by template
- filter by tag
- filter by same area only

## Raw JSON Escape Hatch

The future tool should allow a controlled fallback for advanced fields.

That does not need to be elegant on day one.

It only needs to ensure that uncommon data is not blocked by a narrow structured UI.

## Save Feedback

Saving should be calm and explicit.

Useful feedback later:

- saved successfully
- saved with warnings
- not saved because validation failed
- not saved because preserving unknown fields would be unsafe

## Error Messaging

Prefer concrete messages over vague ones.

Examples of good future errors:

- duplicate entity id `lever_2`
- parameter `target_gate` points to missing entity `gate_99`
- tileset path could not be found under the active project asset roots

## Avoided UX Traps

The future tool should avoid:

- giant forms that expose every field equally
- runtime jargon where a simpler label would work
- silently rewriting unrelated data
- hiding raw values so thoroughly that advanced users are trapped
- making the user type room-local entity ids by hand when a picker would be better
