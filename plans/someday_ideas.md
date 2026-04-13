# Someday Ideas

This is a parking lot for loose ideas that may be worth reconsidering someday.
It is not a roadmap, backlog, promise, or near-term plan.

Do not treat anything here as current behavior or committed future work. Move an
idea into a real plan only after project content creates a concrete need and the
implementation shape has been discussed.

## Ideas

- Entity grouping / group paths: consider a real authored grouping concept for
  entities, probably as a simple string such as `"group": "puzzles/gate_a"` or a
  similar path-like id. This would be more likely to become useful sooner than
  multi-cell occupancy because it can help both runtime authoring and editor
  organization without introducing parent-child ownership. Possible uses include
  grouped entity lists in the editor, selecting or moving a group together, and
  commands that apply work to every entity in a group, such as hiding a whole
  puzzle object or running a command chain for each group member. Prefer flat
  groups over entity-parent hierarchies; avoid implicit transform inheritance,
  lifecycle inheritance, or nested runtime ownership unless a much clearer need
  appears. Atomic group movement, if added, should be designed separately from a
  generic "run command for group members" helper.

- Entity footprints / multi-cell occupancy: someday consider an explicit
  authored footprint for large world entities, separate from sprite size. If this
  ever exists, it should be real occupancy for interaction, queries, collision,
  and editor selection rather than a fake set of blocked cells. Multi-cell
  movement or pushing should be treated as a separate harder problem, not assumed
  as part of the first version.

- Stacked-entity hover picker: temporarily disabled in the editor until a full
  implementation exists. The future version should be visual (not just a plain
  list), support right-click context actions per entity, and stay consistent with
  the new right-click menu behavior.
