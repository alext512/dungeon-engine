# Dialogue Choice Authoring Model

This note explains, in detail, how dialogue choices currently trigger gameplay behavior, why that model feels indirect in some cases, and what alternative designs could improve authoring clarity without losing reuse.

It is intentionally comprehensive. It captures:

- the current active dialogue/controller model
- where `segment_hooks` live and how they are used
- the concrete level 5 controller-lever example from the old reference project
- the exact source of the confusion around `option_id`, caller context, and movement
- the tradeoffs between hooks and inline dialogue commands
- several possible design directions, including a hybrid model

## Scope

Two project surfaces matter here:

- `python_puzzle_engine/` is the active project and engine
- `projects/game_copy/` is the old reference project

The old project is not the active implementation baseline, but it contains a very useful real example of this problem: the level 5 controller lever puzzle.

## Executive Summary

Current behavior:

- Dialogue JSON is primarily content.
- Dialogue behavior is usually attached externally by the caller through `segment_hooks`.
- The dialogue controller owns session state and input routing.
- When the player confirms a choice, the controller resolves the selected `option_id`, looks up the matching hook-provided command list, and executes it.

Why this feels awkward:

- The choice text is in one file.
- The actual behavior is in another file.
- You often cannot tell what a choice does by looking at the dialogue file alone.

Why the current model still exists:

- It keeps dialogue content reusable.
- It lets callers bind the same dialogue to different behaviors.
- It fits the engine's controller-owned state model.

Likely best direction:

- Keep hooks for caller-defined reusable behavior.
- Add optional inline commands for simpler or self-contained dialogues.
- Prefer caller/entity variables over ad hoc "dialogue controller parameters" when inline reusable behavior needs a target entity.

## The Current Active Dialogue Model

The active docs describe the current dialogue model in `AUTHORING_GUIDE.md`.

Relevant sections:

- `AUTHORING_GUIDE.md`, "Starting Dialogue"
- `AUTHORING_GUIDE.md`, "Segment hooks"
- `ENGINE_JSON_INTERFACE.md`, runtime tokens and extra-param forwarding

Key current rules:

1. Some entity calls `run_event` on the dialogue controller.
2. The dialogue controller loads ordinary JSON dialogue data.
3. The controller stores dialogue/session state on itself.
4. The controller temporarily owns relevant input routes.
5. Controller-owned commands render UI and react to later input.

The docs also state that `run_event` and `run_command` forward extra fields as runtime params. That is how the current system passes values like:

- `dialogue_path`
- `dialogue_on_start`
- `dialogue_on_end`
- `segment_hooks`
- `allow_cancel`
- `actor_entity_id`
- `caller_entity_id`

## What a Dialogue File Contains Today

A dialogue file typically contains only content:

```json
{
  "segments": [
    {
      "type": "text",
      "text": "Move the lever?"
    },
    {
      "type": "choice",
      "options": [
        {
          "text": "Move up",
          "option_id": "up"
        },
        {
          "text": "Move right",
          "option_id": "right"
        },
        {
          "text": "Move down",
          "option_id": "down"
        },
        {
          "text": "Move left",
          "option_id": "left"
        },
        {
          "text": "Cancel",
          "option_id": "cancel"
        }
      ]
    }
  ]
}
```

Important implication:

- `option_id` does not itself execute anything.
- It is only an identifier.
- Behavior is resolved elsewhere.

## Where Choice Behavior Actually Lives Today

Current choice behavior usually lives in `segment_hooks`, supplied by the caller.

The docs say:

- each `segment_hooks` entry matches one dialogue segment by index
- a hook may define:
  - `on_start`
  - `on_end`
  - `option_commands_by_id`
  - `option_commands`

This means a choice segment like the second segment above is typically paired with:

```json
{
  "segment_hooks": [
    {},
    {
      "option_commands_by_id": {
        "right": [
          {
            "type": "run_event",
            "entity_id": "ball1",
            "event_id": "push_from_left"
          }
        ]
      }
    }
  ]
}
```

The choice `"right"` works only because:

- the dialogue controller sees that the selected option has `option_id = "right"`
- it looks up `option_commands_by_id["right"]`
- it executes that command list

## Current Runtime Flow for One Choice

The current runtime flow is:

1. Caller entity opens the dialogue through `run_event`.
2. Dialogue controller stores dialogue definition and hook data on itself.
3. Player navigates options through controller-owned input.
4. Player presses confirm.
5. Controller reads selected option.
6. Controller extracts `option_id`.
7. Controller resolves commands from hook data.
8. Command runner executes those commands.

So the command runner is always the thing executing the commands, but the dialogue controller is the owner of the session state and the dispatcher that decides which command list to run.

## The Concrete Level 5 Controller-Lever Example

The clearest real example is in the old reference project:

- `projects/game_copy/areas/level5.json`
- `projects/game_copy/entity_templates/controller_lever.json`
- `projects/game_copy/dialogues/system/controller_lever.json`
- `projects/game_copy/entity_templates/pushable_object.json`

### Dialogue Content

`projects/game_copy/dialogues/system/controller_lever.json`

This file only contains the prompt and the choices:

```json
{
  "segments": [
    {
      "type": "text",
      "text": "Move the lever?"
    },
    {
      "type": "choice",
      "options": [
        { "text": "Move up", "option_id": "up" },
        { "text": "Move right", "option_id": "right" },
        { "text": "Move down", "option_id": "down" },
        { "text": "Move left", "option_id": "left" },
        { "text": "Cancel", "option_id": "cancel" }
      ]
    }
  ]
}
```

No ball movement is authored here.

### Lever Template

`projects/game_copy/entity_templates/controller_lever.json`

The lever template forwards dialogue-related data to the dialogue controller:

```json
{
  "type": "run_event",
  "entity_id": "dialogue_controller",
  "event_id": "open_dialogue",
  "dialogue_path": "$dialogue_path",
  "dialogue_on_start": "$dialogue_on_start",
  "dialogue_on_end": "$dialogue_on_end",
  "segment_hooks": "$segment_hooks",
  "allow_cancel": "$allow_cancel",
  "actor_entity_id": "$actor_id",
  "caller_entity_id": "$self_id"
}
```

Important point:

- `$segment_hooks` here comes from the lever instance data, not from the dialogue file.

### Lever Instance

In `projects/game_copy/areas/level5.json`, `lever1` contains:

```json
{
  "id": "lever1",
  "template": "entity_templates/controller_lever",
  "parameters": {
    "dialogue_path": "dialogues/system/controller_lever.json",
    "dialogue_on_start": [],
    "dialogue_on_end": [],
    "segment_hooks": [
      {},
      {
        "option_commands_by_id": {
          "up": [
            {
              "type": "run_event",
              "entity_id": "ball1",
              "event_id": "push_from_down"
            }
          ],
          "right": [
            {
              "type": "run_event",
              "entity_id": "ball1",
              "event_id": "push_from_left"
            }
          ],
          "down": [
            {
              "type": "run_event",
              "entity_id": "ball1",
              "event_id": "push_from_up"
            }
          ],
          "left": [
            {
              "type": "run_event",
              "entity_id": "ball1",
              "event_id": "push_from_right"
            }
          ]
        }
      }
    ],
    "allow_cancel": true
  }
}
```

So:

- the dialogue file provides `option_id = "right"`
- the lever instance provides the command for `"right"`

### Ball Template

The actual movement is not on the lever and not in the dialogue file. It is in the target object's template:

`projects/game_copy/entity_templates/pushable_object.json`

```json
{
  "events": {
    "push_from_left": {
      "enabled": true,
      "commands": [
        {
          "type": "run_command",
          "command_id": "commands/movement/push_one_tile",
          "direction": "right",
          "frames_needed": "$project.movement.ticks_per_tile"
        }
      ]
    }
  }
}
```

That means the complete `"right"` chain is:

1. Player chooses `"right"` in the dialogue.
2. Dialogue controller resolves selected `option_id = "right"`.
3. Controller executes `option_commands_by_id["right"]`.
4. That calls `run_event(entity_id="ball1", event_id="push_from_left")`.
5. `ball1` uses `pushable_object.json`.
6. `push_from_left` runs `commands/movement/push_one_tile` with `direction = "right"`.
7. The ball moves right.

This is correct and reusable, but the behavior is spread across:

- dialogue file
- lever instance
- ball template

## Why This Feels Confusing

The confusion is not because the engine behavior is undefined. It is because the behavior is distributed across multiple layers.

To answer the simple question:

"What happens if I choose 'right'?"

the author currently has to inspect:

1. the dialogue file
2. the opening entity/template
3. the caller's `segment_hooks`
4. the target entity's event

That is a lot of indirection for a small authored interaction.

## The Actual Role of `option_id`

`option_id` is not behavior.

It is a routing key.

Its job is:

- identify which option was selected
- let the controller look up the matching command list

That is all.

This is why the dialogue file by itself does not tell the whole story.

## Hooks: Strengths and Weaknesses

### What Hooks Are Good At

Hooks are good when:

- the same dialogue content needs different behaviors depending on caller
- the dialogue should stay mostly content-only
- behavior belongs to the caller more than the dialogue asset
- the caller needs to inject setup/cleanup (`dialogue_on_start`, `dialogue_on_end`)

Examples:

- reusable system menus
- generic prefab-like interactive entities
- the same prompt with different targets or outcomes

### What Hooks Are Bad At

Hooks are awkward when:

- the dialogue is one-off
- the dialogue and its behavior are conceptually one authored unit
- the author wants to understand behavior by reading a single file

The most common pain points:

- indirection
- mismatch risk between `option_id` and hook keys
- difficulty tracing cause and effect

## Inline Dialogue Commands

An alternative is to allow commands to live directly inside dialogue content.

For example:

```json
{
  "segments": [
    {
      "type": "text",
      "text": "Move the lever?"
    },
    {
      "type": "choice",
      "options": [
        {
          "text": "Move right",
          "option_id": "right",
          "commands": [
            {
              "type": "run_event",
              "entity_id": "ball1",
              "event_id": "push_from_left"
            }
          ]
        }
      ]
    }
  ]
}
```

This is much easier to read:

- the choice text and behavior are in one place
- there is no second lookup step

## When Inline Commands Are Clearly Better

Inline commands are especially attractive for:

- one-off NPC dialogue
- one-shot cutscene prompts
- bespoke puzzle prompts
- authored story sequences

In those cases, hooks add little value and mostly add indirection.

## One-Off Inline vs Reusable Inline

There are two useful inline-command patterns:

### 1. One-Off Inline

Best when the dialogue is authored for one exact situation.

Example:

- one NPC asks one unique question
- the "Yes" choice triggers one fixed cutscene or state change

### 2. Reusable Inline

Best when the dialogue owns the behavior pattern, but some data changes.

Example:

- same "Move the lever?" dialogue
- same directional behavior
- different lever instances target different balls

In that model, the dialogue remains reusable, but the variability is treated as data rather than hook-injected logic.

## The Real Problem with "Random Dialogue Controller Params"

One possible inline design would pass extra top-level fields through `open_dialogue`, such as:

```json
{
  "type": "run_event",
  "entity_id": "dialogue_controller",
  "event_id": "open_dialogue",
  "dialogue_path": "$dialogue_path",
  "dialogue_params": {
    "target_ball_id": "$target_ball_id"
  },
  "allow_cancel": "$allow_cancel",
  "actor_entity_id": "$actor_id",
  "caller_entity_id": "$self_id"
}
```

This works conceptually, but it creates a design smell if taken too far:

- `target_ball_id`
- `target_gate_id`
- `shop_id`
- `reward_id`
- `quest_id`
- etc.

If every special case becomes a top-level dialogue-open field, the dialogue controller surface becomes cluttered with arbitrary caller-specific payload.

That is not a good long-term shape.

## A Better Reusable-Inline Fit: Use Caller Variables

The current token system already supports:

- `$caller_id`
- `$caller.some_var`

The docs explicitly state that:

- `$self...`
- `$actor...`
- `$caller...`

read entity `variables`

That means a cleaner reusable-inline model is:

1. Store target data as variables on the caller entity.
2. Pass `caller_entity_id` as normal.
3. Let inline commands read `$caller.some_var`.

Example:

### Lever Template

```json
{
  "variables": {
    "blocks_movement": true,
    "target_ball_id": "$target_ball_id"
  },
  "events": {
    "interact": {
      "enabled": true,
      "commands": [
        {
          "type": "run_event",
          "entity_id": "dialogue_controller",
          "event_id": "open_dialogue",
          "dialogue_path": "$dialogue_path",
          "allow_cancel": "$allow_cancel",
          "actor_entity_id": "$actor_id",
          "caller_entity_id": "$self_id"
        }
      ]
    }
  }
}
```

### Dialogue File

```json
{
  "segments": [
    {
      "type": "text",
      "text": "Move the lever?"
    },
    {
      "type": "choice",
      "options": [
        {
          "text": "Move right",
          "option_id": "right",
          "commands": [
            {
              "type": "run_event",
              "entity_id": "$caller.target_ball_id",
              "event_id": "push_from_left"
            }
          ]
        }
      ]
    }
  ]
}
```

This is attractive because:

- the dialogue controller stays generic
- no extra session-specific schema is required
- the caller already exists in the runtime model
- the dialogue stays reusable as long as callers expose the expected variables

## Important Caveat: This Is Not Implemented Today

The existing system does not currently support inline option commands in dialogue JSON.

Right now:

- the dialogue controller expects choice commands to come from hooks
- `confirm_choice` resolves command lists from hook data

So the reusable-inline pattern described above is conceptually compatible with the runtime model, but it would still require implementation work.

## What Would Need to Change for Inline Commands

At a high level:

1. The dialogue loader/segment-prep step would need to read inline commands from the selected segment or option.
2. The confirm-choice path would need to prefer:
   - hook-provided commands when present
   - otherwise inline option commands
3. The controller would execute that resolved list exactly the same way it already executes hook-provided commands.

This means inline commands do not require a totally separate execution system.

They are mostly a new source for the command list the controller already runs.

## A Practical Hybrid Model

The most compelling model is probably hybrid:

### Use inline commands when:

- the dialogue owns the behavior
- the dialogue is one-off or mostly self-contained
- the behavior is easier to understand when authored beside the text

### Use hooks when:

- the caller should fully decide behavior
- the same dialogue content needs materially different logic in different contexts
- the dialogue should remain presentation-only

### Suggested precedence rule

If both exist:

1. hook-provided commands override inline commands
2. inline commands serve as the default authored behavior

That gives:

- simple authoring by default
- reusable caller overrides when needed

## Where Each Style Fits Best

### Hooks-only is best for:

- system menus
- generic prefab UIs
- cases where the same dialogue text is reused with substantially different logic

### Inline-only is best for:

- fixed one-shot story moments
- highly specific NPC interactions
- puzzle prompts whose behavior is part of the content itself

### Reusable-inline is best for:

- same behavior pattern, different target data
- prompts like:
  - "Move the lever?"
  - "Open this gate?"
  - "Teleport here?"
  - "Buy this item?"

where:

- the logic is stable
- only IDs or values vary

## Recommended Direction

Recommendation:

1. Keep the current hook system.
2. Add optional inline commands for dialogue choices.
3. Prefer caller/entity variables over ad hoc dialogue-open payload fields when reusable inline behavior needs data.
4. Use hooks as the advanced override mechanism, not the only authoring path.

Reasoning:

- This keeps current reusable controller patterns working.
- It improves readability for one-off and dialogue-owned behavior.
- It avoids bloating the dialogue controller with endless one-off open params.
- It aligns better with how authors naturally think about many dialogue choices.

## The Core Insight

The problem is not that hooks are wrong.

The problem is that hooks are currently carrying too much of the everyday authoring burden, including cases where the most natural home for the behavior is the dialogue file itself.

Hooks should remain available.

They probably should not remain the only way choice behavior is authored.

## Short Version

If the question is:

"What should the system optimize for?"

the answer is:

- optimize for readability first in common authored cases
- keep hooks for reuse and override power

That points strongly toward a hybrid model:

- inline commands for normal dialogue-owned behavior
- hooks for caller-owned behavior

