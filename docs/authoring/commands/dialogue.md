# Dialogue Commands

Dialogue commands open and close the engine-owned dialogue UI, or choose which
entity-owned dialogue should be used next.

Use this page with:

- [Command System](../command-system.md) for command-chain timing
- [Dialogue And Inventory UI](../dialogue-inventory-ui.md) for authored dialogue data
- [Runtime Tokens](../reference/runtime-tokens.md) for values like `$self_id`
- [Save State](../reference/builtin-commands.md#reset-and-persistence-helpers)
  when a dialogue choice should survive between play sessions

## Two Common Dialogue Shapes

### Direct Dialogue Sessions

Use `open_dialogue_session` when the command itself names the dialogue file or
contains the inline dialogue definition.

This is useful for menus, cutscenes, one-off messages, and project commands that
do not belong to one specific NPC.

### Entity-Owned Dialogues

Use `open_entity_dialogue` when an entity owns a `dialogues` map. This is the
usual NPC pattern.

An entity can also keep a variable named `active_dialogue`. If
`open_entity_dialogue` has no `dialogue_id`, it opens the dialogue whose id is
stored in `active_dialogue`.

The active-dialogue commands change that variable. They do not open a dialogue
by themselves.

## open_dialogue_session

Starts a dialogue session from either a project dialogue file or an inline
dialogue definition.

Use this when the command chain knows exactly what dialogue should open.

Important fields:

- `dialogue_path`: project-relative path to a dialogue JSON file
- `dialogue_definition`: inline dialogue definition object
- `dialogue_on_start`: optional commands that run when the session starts
- `dialogue_on_end`: optional commands that run when the session ends
- `allow_cancel`: whether the player can cancel out of the session
- `actor_id`: entity shown or treated as the speaker/actor
- `caller_id`: entity treated as the command caller
- `ui_preset`: optional dialogue UI preset name

Use exactly one of `dialogue_path` or `dialogue_definition`.

Example:

```json
{
  "type": "open_dialogue_session",
  "dialogue_path": "dialogues/system/title_menu.json",
  "allow_cancel": false
}
```

Related commands:

- [`close_dialogue_session`](#close_dialogue_session)
- [`open_entity_dialogue`](#open_entity_dialogue)

## close_dialogue_session

Closes the currently active dialogue session.

Use this from dialogue hooks, option commands, or screen UI commands when the
current dialogue should end early. If you just want a normal dialogue option to
finish, prefer the dialogue option's own close/end behavior.

Example:

```json
{
  "type": "close_dialogue_session"
}
```

Related commands:

- [`open_dialogue_session`](#open_dialogue_session)
- [`open_entity_dialogue`](#open_entity_dialogue)

## open_entity_dialogue

Opens one dialogue from an entity's authored `dialogues` map.

Use this for NPC interaction, signs, inspectable objects, and any entity whose
dialogue should live with the entity or template.

Important fields:

- `entity_id`: entity that owns the `dialogues` map
- `dialogue_id`: optional named dialogue entry on that entity
- `dialogue_on_start`: optional commands that run when the session starts
- `dialogue_on_end`: optional commands that run when the session ends
- `allow_cancel`: whether the player can cancel out of the session
- `actor_id`: optional speaker/actor override
- `caller_id`: optional caller override
- `ui_preset`: optional dialogue UI preset name

If `dialogue_id` is omitted, the command reads the entity variable
`active_dialogue`.

Example:

```json
{
  "type": "open_entity_dialogue",
  "entity_id": "old_miner"
}
```

With an explicit dialogue id:

```json
{
  "type": "open_entity_dialogue",
  "entity_id": "old_miner",
  "dialogue_id": "after_gate_opens"
}
```

Related commands:

- [`set_entity_active_dialogue`](#set_entity_active_dialogue)
- [`step_entity_active_dialogue`](#step_entity_active_dialogue)
- [`set_entity_active_dialogue_by_order`](#set_entity_active_dialogue_by_order)

## set_entity_active_dialogue

Sets which named dialogue an entity will use when `open_entity_dialogue` opens
that entity without an explicit `dialogue_id`.

Use this when an NPC has several dialogue entries and gameplay should choose the
next one, for example after a quest step, after opening a gate, or after the
player picks up an item.

This command changes the entity variable `active_dialogue`. It does not open the
dialogue by itself.

Important fields:

- `entity_id`: entity whose active dialogue should change
- `dialogue_id`: named dialogue entry on that entity
- `persistent`: optional save override

When `persistent` is omitted, the command follows that entity's Save State rule
for the `active_dialogue` variable. Set `persistent` explicitly only when this
one command should override the entity's normal rule.

Example:

```json
{
  "type": "set_entity_active_dialogue",
  "entity_id": "old_miner",
  "dialogue_id": "after_gate_opens"
}
```

A common pattern is to set the active dialogue during some other gameplay flow,
then let the normal interaction command open it later:

```json
[
  {
    "type": "set_entity_active_dialogue",
    "entity_id": "old_miner",
    "dialogue_id": "thanks_for_help"
  },
  {
    "type": "set_entity_var",
    "entity_id": "old_miner",
    "name": "quest_finished",
    "value": true
  }
]
```

Related commands:

- [`open_entity_dialogue`](#open_entity_dialogue)
- [`step_entity_active_dialogue`](#step_entity_active_dialogue)
- [`set_entity_active_dialogue_by_order`](#set_entity_active_dialogue_by_order)

## step_entity_active_dialogue

Moves an entity's active dialogue forward or backward through that entity's
authored dialogue order.

Use this for simple cycling behavior, such as rotating between several sign
messages or advancing an NPC through a short list of conversation states.

This command changes the entity variable `active_dialogue`. It does not open the
dialogue by itself.

Important fields:

- `entity_id`: entity whose active dialogue should change
- `delta`: how far to move through the authored order; defaults to `1`
- `wrap`: whether moving past either end wraps around
- `persistent`: optional save override

Example:

```json
{
  "type": "step_entity_active_dialogue",
  "entity_id": "old_miner",
  "delta": 1,
  "wrap": true
}
```

Related commands:

- [`set_entity_active_dialogue`](#set_entity_active_dialogue)
- [`set_entity_active_dialogue_by_order`](#set_entity_active_dialogue_by_order)
- [`open_entity_dialogue`](#open_entity_dialogue)

## set_entity_active_dialogue_by_order

Sets an entity's active dialogue using the human-facing 1-based order shown in
the editor.

Use this when the order is the important thing, such as "use the second authored
dialogue entry". Prefer `set_entity_active_dialogue` when you want the reference
to survive future reordering.

This command changes the entity variable `active_dialogue`. It does not open the
dialogue by itself.

Important fields:

- `entity_id`: entity whose active dialogue should change
- `order`: 1-based dialogue order
- `wrap`: whether out-of-range values wrap around the dialogue list
- `persistent`: optional save override

Example:

```json
{
  "type": "set_entity_active_dialogue_by_order",
  "entity_id": "old_miner",
  "order": 2
}
```

Related commands:

- [`set_entity_active_dialogue`](#set_entity_active_dialogue)
- [`step_entity_active_dialogue`](#step_entity_active_dialogue)
- [`open_entity_dialogue`](#open_entity_dialogue)
