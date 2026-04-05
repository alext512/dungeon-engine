# Future Deprecations

This note tracks authoring/runtime surfaces that are still supported today but
are candidates for replacement or removal once better workflows exist.

## Area `entry_points`

Current status:
- supported by the runtime
- documented
- still used by `change_area(entry_id=...)` and `new_game(entry_id=...)`

Why it may be deprecated later:
- it is abstract and easy to lose track of in the editor
- it is less spatially clear than targeting a real marker entity in the
  destination area
- destination-marker entities can participate in existing entity workflows:
  placement, movement, ids, future pickers, and visual authoring cues

Preferred future direction:
- use destination marker entities in the target area
- target them through transition commands with `destination_entity_id`
- keep `entry_points` only as a compatibility surface until projects and tools
  have fully moved over

Important note:
- `entry_points` are not deprecated yet
- they remain fully supported for now
- this document is only recording the intended future direction
