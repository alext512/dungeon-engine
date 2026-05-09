# Command Pages

These pages are the editor-friendly command wiki. Use them when you want more
than the quick command inventory, but less than the full engine contract.

Each command page should answer:

- what the command does
- when to use it
- what it does not do
- the important fields
- a small JSON example
- related commands and concepts

## Command Families

- [Dialogue Commands](dialogue.md) for opening dialogue sessions and choosing
  entity-owned dialogue entries
- [Movement Commands](movement.md) for entity position primitives, grid motion,
  and common movement project-command presets
- [Camera Commands](camera.md) for camera policy, movement, and common camera
  project-command presets
- [Entity Field Commands](entity-fields.md) for entity state primitives and
  common field project-command presets
- [Variable Commands](variables.md) for current-area/entity variable writes and
  common variable project-command presets

## Related Reference

- [Command System](../command-system.md) explains how command chains run.
- [Built-in Commands](../reference/builtin-commands.md) is the quick inventory.
- [Engine JSON Interface](../manuals/engine-json-interface.md) is the canonical
  exact contract.
