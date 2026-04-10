# Authoring Workflow

This page describes a practical way to build content with the current engine.

## Start Small

A good first playable slice is:

1. one `project.json`
2. one area
3. one player template
4. one set of input routes
5. one interactable object
6. one dialogue or transition

Avoid designing a whole game before you can run one room end to end.

## Suggested Project Build Order

### 1. Create `project.json`

Define where the engine should look for:

- areas
- entity templates
- commands
- items
- assets
- shared variables

### 2. Create a playable starting area

An area usually needs:

- at least one tileset
- one or more tile layers
- a player entity instance
- input routing for the actions you want active

Minimal example:

```json
{
  "entities": [
    {
      "id": "player_1",
      "grid_x": 2,
      "grid_y": 4,
      "template": "entity_templates/player"
    }
  ],
  "input_targets": {
    "move_up": "player_1",
    "move_down": "player_1",
    "move_left": "player_1",
    "move_right": "player_1",
    "interact": "player_1",
    "inventory": "player_1"
  }
}
```

### 3. Create reusable entity templates

Use templates for things such as:

- players
- doors and transitions
- switches and puzzle targets
- controller entities
- pickups or interactables

The repo-local `entity_templates/player.json` is a good example because it shows:

- visuals
- input mapping
- entity-owned inventory
- named entity commands

### 4. Add behavior through commands

Most game logic should live in command chains, not in custom engine code.

Common places where commands appear:

- `entity_commands`
- area `enter_commands`
- project command files
- item `use_commands`
- dialogue hooks and option commands

### 5. Add content types only when needed

Use these progressively:

- `dialogues/` for dialogue and menu data
- `items/` for inventory item definitions
- `commands/` for reusable project-wide command chains
- `shared_variables.json` for project-wide config, presets, and shared values

## When To Use The Editor

The editor is already the best choice for:

- painting tile maps
- editing cell flags
- placing and nudging entities
- adjusting render properties
- editing project manifest basics
- editing shared variables, items, and global entities
- safe rename or move operations for file-backed content

## When Raw JSON Is Still The Better Tool

Use raw JSON directly when you need:

- deeper or newer command shapes
- advanced dialogue/menu data structures
- engine surfaces the editor does not structure yet
- debugging of exact saved or authored payloads

The editor is intentionally conservative. It should not pretend to fully understand every JSON shape if that would risk destructive rewrites.

## A Good Pattern For Puzzle Objects

For a simple object such as a lever or floor switch:

- put reusable visuals and default behavior in the template
- expose the tuning points as parameters
- let placement decide which target entity or area it affects

That keeps the content reusable instead of cloning one-off entities everywhere.

## A Good Pattern For Project Growth

- Build one vertical slice.
- Reuse it in two or three rooms.
- Notice what becomes repetitive.
- Turn the repetitive part into a template, project command, or shared preset.

That is usually a better path than trying to invent every abstraction on day one.

## Deeper References

When you need the full long-form material, go straight to:

- [Authoring Guide](manuals/authoring-guide.md)
- [Engine JSON Interface](manuals/engine-json-interface.md)
