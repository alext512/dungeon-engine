# Area And Screen-Space UX/UI Plan

This document defines the concrete UX/UI plan for the next editor slice:

- new area creation
- directional area growth/shrink
- screen-space entity creation and placement

It is intentionally practical and implementation-oriented.

## UX Goal

The user should be able to:

1. create a new area without touching JSON
2. expand or trim the area bounds in explicit directions
3. place screen-space entities visually in the screen pane
4. keep using the same overall editor mental model

This should feel like a natural extension of the current editor, not a separate
tool mode or a special title-screen editor.

## UX Principles

1. **Prefer explicit actions over abstract resize math.**
   Users should choose `Add Rows Above...`, not decipher anchor-based resizing.

2. **Keep the existing center of gravity.**
   The canvas, template panel, layer panel, and selected-entity workflow should
   still feel familiar.

3. **Treat screen-space entities as normal entities.**
   They differ in placement rules, not in editor status or special-case
   identity.

4. **Use small dialogs for setup, not large configuration surfaces.**
   The user should answer a few practical questions and then continue editing
   visually.

5. **Keep title/start screens generic.**
   The editor should not grow a dedicated “main menu builder.” Users should
   compose these screens from normal templates and normal placement tools.

## Main Window Additions

This slice should add UI in three places:

- menu bar
- canvas behavior
- status/help feedback

No new major dock panels are required.

## 1. New Area UX

## Menu Placement

Add:

- `File > New Area...`

Rationale:

- this is a file/content creation action
- it matches user expectations better than hiding it under `Edit`

The action should be disabled when no project is open.

## Dialog Layout

The `New Area...` dialog should be small and simple.

Fields:

- `Area ID`
- `Display Name`
- `Width`
- `Height`
- `Tile Size`
- `Include Default Ground Layer`

Recommended layout:

- form-style vertical dialog
- OK / Cancel buttons

Recommended defaults:

- width: `20`
- height: `15`
- tile size: `16`
- include default ground layer: enabled

## Validation UX

Validation should happen before close, with direct warning messages.

Rules:

- Area ID must not be empty
- Area ID must not collide with an existing area
- width and height must be at least `1`
- tile size must be at least `1`

First pass can use message boxes instead of inline field errors.

## Success Flow

On successful creation:

1. close dialog
2. refresh Areas panel
3. open the new area in a tab
4. select/highlight it in the Areas panel
5. make the canvas active immediately

The user should feel like they created a room and are now ready to work in it.

## 2. Directional Area Growth/Shrink UX

## Menu Placement

Add a new top-level menu:

- `Area`

This menu should contain:

- `Add Rows Above...`
- `Add Rows Below...`
- `Add Columns Left...`
- `Add Columns Right...`
- separator
- `Remove Top Rows...`
- `Remove Bottom Rows...`
- `Remove Left Columns...`
- `Remove Right Columns...`

Rationale:

- these are area-shape operations, not generic edit commands
- this groups them clearly without cluttering `Edit`

All actions should be disabled when no area tab is active.

## Dialog Style

Each action should open a tiny dedicated dialog rather than one generic resize
window.

Fields:

- count to add/remove

Text should explicitly name the direction, for example:

- `Add 3 rows above the current area`
- `Remove 2 columns from the right side`

## Warning UX

Removal actions may need warnings.

Two different warning situations should be surfaced clearly:

### Tile Loss Warning

Removing rows/columns will discard tiles on that side.

This is expected behavior, but the dialog text should make it obvious before
the user confirms.

### Entity Block Warning

If the removal would push world-space entities out of bounds, the operation
should be blocked with a warning message.

The first version should **not** silently delete or clamp entities.

Example message:

- `Cannot remove left columns because 2 world-space entities would end up outside the area bounds.`

## Post-Operation UX

After a successful add/remove operation:

- area tab becomes dirty
- canvas refreshes immediately
- selection stays active when possible
- if the selected world-space entity was shifted, the inspector updates to the
  new coordinates
- status bar may briefly show a message like:
  - `Added 2 rows above`
  - `Removed 1 column from the right`

## 3. Screen-Space Entity Placement UX

## Goal

The user should be able to use the existing Templates panel to place
screen-space entities in the screen pane just as naturally as world-space
templates are placed in the world grid.

## Template Selection UX

When the user clicks a template in the Templates panel:

- world-space template:
  - current behavior remains
- screen-space template:
  - the template brush should still activate
  - it should no longer be presented as unsupported

The status bar should clearly indicate the active template brush in both cases.

## Canvas Placement UX

When a screen-space template brush is active:

- clicking in the **screen pane** places a new entity
- clicking in the world grid does **not** place that entity

This makes the placement intent unambiguous.

## Placement Position Rule

For V1:

- use the clicked screen-pane pixel coordinate as the new entity's
  `pixel_x` / `pixel_y`

Do not attempt automatic centering based on sprite size yet.

This keeps placement predictable and simple.

## Selection UX

After placing a screen-space entity:

- it should become the selected entity immediately
- the selected-entity panel should update
- the status bar should reflect the new selection

This matches the feeling of “I placed this, now I can tweak it.”

## Movement UX

For this slice, the minimum required movement workflow is:

- select screen-space entity in the screen pane
- nudge it using the existing commands/mechanics

If drag-move is trivial, it can be added.

If not, drag-move should be deferred rather than half-implemented.

## Hover / Active Feedback

When a screen-space template is the active brush:

- the screen pane should feel like the active target
- status text should not say the template is unsupported
- the user should not need to infer special rules from trial and error

Helpful status examples:

- `Paint: entity title_logo`
- `Click in the screen pane to place`

The second line/message is optional but would be a nice touch.

## Screen Pane Rules

### Allowed

- select screen-space entities
- place screen-space entities
- nudge selected screen-space entities

### Not Part Of This Slice

- drag-select multiple entities
- box layout tools
- snapping/alignment guides
- layer groups for UI screens
- anchor/pivot controls

These can come later if real use shows they are needed.

## 4. Status And Discoverability

This slice should use small feedback improvements to reduce ambiguity.

Recommended:

- brief status-bar confirmation after:
  - area creation
  - area growth/shrink
  - screen-space placement
- keep template brush status text accurate for screen-space templates

Examples:

- `Created area areas/title_screen`
- `Added 4 columns left`
- `Placed screen entity title_logo_1`

## 5. Error Handling UX

Error handling should stay direct and conservative.

Use warning dialogs for:

- invalid new-area input
- duplicate area id
- blocked removal because of out-of-bounds entities
- failed screen-space placement if a template/config issue occurs

The first version does not need inline validation or fancy recovery UI.

## 6. Non-Goals For UX

This slice should not try to design:

- a dedicated title-screen mode
- a dedicated main-menu authoring mode
- import wizards
- asset-copy/import flows
- generic scene templates
- layout snapping/alignment systems

The UX should stay focused on enabling normal authored content workflows.

## Recommended Implementation Order

1. `New Area...`
2. directional area add/remove actions
3. screen-space template placement

This order is also the best UX-risk order:

- area creation is simplest and most self-contained
- directional grid tools are explicit and low-ambiguity
- screen-space placement is the most interaction-sensitive and benefits from
  being implemented after the easier surfaces are stable

## Confidence Notes

Confidence is highest for:

- new area dialog UX
- directional growth/shrink UX

Confidence is slightly lower, but still good, for:

- exact feel of screen-space placement in the canvas

That part is likely to need small tuning during implementation, but the
intended user-facing behavior is already clear enough to proceed.
