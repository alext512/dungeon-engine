# Dialogue UI Rework Direction

This document captures the current agreed direction for the dialogue and menu UI
rework.

It is a planning document, not the canonical implementation reference.
The active docs should only be updated after the implementation changes are
real.

This document is intentionally focused on:

- session ownership
- UI ownership
- layout presets
- portraits
- option presentation
- the boundary between engine runtime and authored JSON

It does not replace `plans/dialogue_choice_authoring_model.md`.
That document should be preserved and revisited later when implementing the
final command/hook model for dialogue choices.

## Why This Rework Exists

The current dialogue controller entity is doing too much generic runtime work.

It currently acts as:

- session manager
- input owner
- page and choice state container
- nested dialogue stack owner
- render coordinator
- choice-command dispatcher

That makes ordinary dialogue authoring more indirect and more engine-internal
than it should be.

The rework should move generic session machinery into the engine while keeping
dialogue content, presentation choices, and gameplay outcomes in authored JSON.

## Core Direction

The engine should own the generic dialogue and menu session runtime.

Projects should own:

- dialogue content
- menu content
- UI presets
- portraits
- hooks and outcomes
- game-specific logic

This means the project should stop having to author a full dialogue session
state machine through a special screen-space controller entity.

## Engine-Owned Dialogue Runtime

The engine should own the generic session mechanics for dialogue and menu flows.

That includes:

- open/close state
- active dialogue or menu definition
- current segment
- current page
- selected option index
- choice scroll window
- confirm/cancel/advance behavior
- timed advance support
- modal input capture and restore
- generic pagination and choice navigation behavior

The engine should not own:

- story meaning
- puzzle meaning
- specific dialogue outcomes
- project-specific UI art/style decisions

## Current Dialogue Controller

The current dialogue controller entity should likely stop existing as the live
owner of dialogue session state.

Preferred direction:

- remove the current dialogue controller as a runtime state machine
- replace it with engine-owned session state plus project-authored dialogue UI
  config/data

Possible remaining project-owned pieces:

- UI preset data
- panel assets
- fonts/colors
- helper commands for dialogue outcomes

But not the session machine itself.

## UI Ownership

For the simple dialogue case, the project should decide how dialogue looks.

Project-owned UI concerns include:

- panel image
- panel size
- panel position
- font
- text color
- choice color
- text width
- maximum visible text lines
- portrait slot position and size
- choice list position and size
- visible choice rows
- row height
- overflow behavior

The engine should decide how those settings are used consistently, not what
those settings are.

## UI Presets

The project should be able to define multiple named dialogue UI presets.

Recommended model:

- one preset may be the project default
- dialogues may choose a preset explicitly
- later, small per-dialogue overrides may be allowed on top

Why presets are better than one global layout:

- different dialogue or menu styles can coexist
- current "choices inside the dialogue panel" can remain the default
- future narration/menu/system prompts can use different layouts

Why presets are better than automatic layout selection:

- explicit and predictable
- easier to author
- easier to debug
- less magic

The engine should not automatically pick layouts based on text length or option
count.

## Portraits

Portrait layout belongs to the UI preset.

That means the preset may define:

- whether there is a portrait slot
- where it is
- how large it is
- how text layout changes when a portrait is present

For now, portrait art itself should stay explicit in dialogue content rather
than being routed through a speaker or portrait registry.

So the current preferred direction is:

- UI preset owns the portrait slot layout
- dialogue content owns the portrait image path and related per-segment portrait
  data

Speaker-definition indirection may be added later if it becomes worth it, but it
is not required for the first rework slice.

## Dialogue Options

Choice segments should stay part of the same dialogue/menu session system.

The engine should own:

- selected option index
- moving selection
- choice scrolling
- confirm/cancel behavior
- resolving the selected option

The project should own:

- option text
- option ids
- how options are visually presented through the selected UI preset
- what each option does

Important:

- choice mechanics and choice presentation should be separate
- current "choices in the same dialogue panel" is a good default, but should be
  expressed by presets rather than hardcoded into the session logic

## Choice Layout Behavior

Recommended direction:

- presets define whether choices are inline or in a separate panel
- presets define visible rows, row height, width, and layout coordinates
- the engine handles scroll windows and selection movement

For long option text, the preferred default is:

- single-line option rows
- selected long options may use marquee-style horizontal scrolling
- avoid multi-line wrapped choice rows by default

Wrapped multi-line options can remain a possible later extension, but they
should not be the default because they complicate navigation and row sizing.

## Commands In Dialogues

This document now locks the broad command-binding direction for dialogues.

This topic should still be implemented carefully and should be informed by
`plans/dialogue_choice_authoring_model.md`.

Important preserved decision:

- do not forget the earlier dialogue choice authoring discussion, especially
  the reusable-inline pattern
- preserve it as part of the planned design space for the new dialogue system

The locked direction is a hybrid model involving:

- whole-dialogue caller hooks
- caller-provided segment hooks
- optional inline dialogue-owned commands

The important planned inline modes are:

- one-off inline commands for dialogue-owned behavior
- reusable inline commands that read data from `$caller...` or other entity
  variables instead of requiring endless custom `open_dialogue` payload fields

The system should avoid turning `open_dialogue` into a dumping ground for
arbitrary special-purpose top-level parameters.

### Precedence Rule

If both caller-provided hook commands and inline dialogue-owned commands exist
for the same scope:

- caller-provided hook commands should override inline commands
- inline commands should act as the default authored behavior
- both should not run by default

This keeps dialogue-owned behavior simple by default while preserving caller
override power for reusable content.

### Dialogue Command Sources

Under the new dialogue system, the planned command sources are:

1. whole-dialogue caller hooks
2. caller-provided segment hooks
3. inline dialogue-owned commands

That third source includes both:

- segment-level inline commands such as `on_start` and `on_end`
- option-level inline `commands`

### Recommended Fit

Use whole-dialogue caller hooks for:

- setup around opening the session
- cleanup after closing the session
- outer-context behavior that belongs to the caller, not the dialogue file

Use caller-provided segment hooks for:

- reusable dialogue content whose meaning varies by caller
- system menus and prefab prompts
- caller-owned overrides for specific segments or options

Use inline dialogue-owned commands for:

- one-off story moments
- self-contained puzzle prompts
- authored behavior that is easiest to understand beside the text itself

Use reusable-inline patterns when:

- the behavior pattern is stable
- only data changes between callers
- the dialogue can read that data through `$caller...` or other existing entity
  variable surfaces

## Common Dialogue Shape

The new dialogue data should prefer one common `segments` shape rather than
multiple unrelated top-level formats.

Recommended direction:

- each dialogue contains a `segments` array
- each segment has a `type`
- common fields such as `text`, `speaker_id`, `portrait`, `on_start`, and
  `on_end` may appear where relevant
- choice segments additionally contain `options`

Representative shape:

```json
{
  "ui_preset": "standard",
  "segments": [
    {
      "type": "text",
      "speaker_id": "guard",
      "portrait": {
        "path": "assets/project/portraits/guard.png",
        "frame_width": 38,
        "frame_height": 38,
        "frame": 0
      },
      "text": "Halt. The gate is sealed.",
      "advance": {
        "mode": "interact"
      },
      "on_start": [],
      "on_end": []
    },
    {
      "type": "choice",
      "speaker_id": "guard",
      "portrait": {
        "path": "assets/project/portraits/guard.png",
        "frame_width": 38,
        "frame_height": 38,
        "frame": 0
      },
      "text": "What do you want to do?",
      "options": [
        {
          "text": "Open the gate",
          "option_id": "open",
          "commands": []
        },
        {
          "text": "Leave",
          "option_id": "leave",
          "commands": []
        }
      ],
      "on_start": [],
      "on_end": []
    }
  ]
}
```

The exact final field list may still evolve, but the direction should remain:

- one common segment model
- predictable optional fields
- no need for separate dialogue dialects

## Cancel Policy

The current preferred cancel policy for the new dialogue system is:

- `allow_cancel: false` means cancel input does nothing
- `allow_cancel: true` means cancel closes the current dialogue or menu session
  by default

This avoids forcing every choice prompt to define a separate explicit cancel
option.

If special cancel behavior is needed later, it can be added deliberately rather
than becoming part of the default rule now.

## Nested Sessions

Nested dialogues and menus should still be supported.

The intended runtime behavior is:

- opening a nested dialogue or submenu pushes the current session onto a stack
- the child session becomes active
- when the child session closes, the parent session resumes cleanly

The exact internal implementation details can wait for coding, but the intended
runtime behavior should remain stack-based.

## Choice Layout Preset Schema

The UI preset should explicitly define choice layout behavior rather than making
the engine infer it automatically.

Typical preset-controlled fields include:

- whether choices are inline or in a separate panel
- choice panel position and size when applicable
- list position and width
- visible row count
- row height
- overflow behavior such as marquee on the selected option

This should remain explicit and predictable rather than heuristic.

## Escape Hatch Rule

The dialogue/UI rework should preserve the current ability for advanced authors
to build unusual behavior with low-level commands.

The intended model is:

- standard dialogue and menu sessions become easier and more explicit
- advanced projects may still bypass or extend the standard session machinery
  when needed

The system should become easier by default, not weaker overall.

## Immediate Next Discussion

The next design discussion after this document should be:

- where dialogue-triggered commands live
- how caller hooks, segment hooks, and inline commands should coexist
- how the reworked session system should dispatch those behaviors
