# Reference Overview

This section is the quick-reference layer of the docs site.

## Use This Section When You Need Exact Surfaces

- [Project Manifest](project-manifest.md) for `project.json`
- [Content Types](content-types.md) for areas, templates, commands, items, and ordinary project JSON
- [Built-in Commands](builtin-commands.md) for the runtime command inventory
- [Runtime Tokens](runtime-tokens.md) for command-time lookups and structured value sources

## Canonical Truth Model

The repo already has a documentation truth order, and it is worth preserving:

- canonical contract/reference docs should stay closest to implementation reality
- author-facing workflow docs should explain how to use the current contract
- planning docs should stay clearly future-facing
- historical docs should not be mistaken for current behavior

The current canonical long-form references are:

- [Engine JSON Interface](../manuals/engine-json-interface.md)
- [Authoring Guide](../manuals/authoring-guide.md)
- [README.md](https://github.com/alext512/dungeon-engine/blob/main/README.md)

## If You Are Working With Agents

The most useful agent-facing references are:

- [For Coding Agents](../architecture/for-coding-agents.md)
- [Docs Maintenance](../contributing/docs-maintenance.md)

Those pages explain what is canonical, what must be updated when behavior changes, and what validation steps matter before declaring a docs or command-surface change safe.
