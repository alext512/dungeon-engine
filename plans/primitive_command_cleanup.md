# Temporary Plan — Primitive Command Cleanup

This is a temporary planning note.

Its purpose is to capture the pending command-system cleanup we have recently discussed, without pretending that the work is already implemented or that the permanent docs have already been updated.

This file should be deleted once:
- the implementation is finished
- the permanent docs have been updated to reflect the final result

## Completed Slices So Far

- variable primitives were tightened first:
  - broad `set_var` / `increment_var` / `check_var` style commands were replaced by explicit world/entity forms
- entity-target mutation and input-routing primitives were tightened next:
  - strict primitives such as `set_entity_field`, `set_event_enabled`, `set_input_target`, and `route_inputs_to_entity` now require explicit ids or resolved `$..._id` tokens
  - raw symbolic `self` / `actor` / `caller` ids are now rejected at startup validation and runtime for those primitives
- camera follow/query primitives were tightened after that:
  - the old explicit follow primitive was later replaced by structured `set_camera_follow` / `set_camera_state`
  - broad `set_var_from_camera` was replaced by `set_world_var_from_camera` and `set_entity_var_from_camera`
- visual/animation primitives were tightened next:
  - strict primitives such as `set_facing`, `play_animation`, `wait_for_animation`, `stop_animation`, `set_visual_frame`, and `set_visual_flip_x` now also require explicit ids or resolved `$..._id` tokens
- movement primitives were tightened after that:
  - strict primitives such as `move_entity_one_tile`, `move_entity`, `teleport_entity`, and `wait_for_move` now also require explicit ids or resolved `$..._id` tokens

The remaining work is about the other primitive families, not these completed slices.

## Why This Exists

The current command system works, but many builtin/primary commands have become too broad.

Some primitive commands currently accept:
- symbolic target resolution
- broad runtime context
- extra parameters that belong to other command families

This makes the engine API feel less like a set of clear primitives and more like a permissive mini scripting layer.

That is drifting away from the intended spirit of the project.

## Main Direction We Agreed On

### 1. Primitive Commands Should Be Truly Primitive

Primary/builtin engine commands are the engine API.
They should:
- take only the arguments they directly need
- do one clear engine operation
- not expose broad magical context "just in case"

Examples of the desired feel:
- set one entity variable
- set one world variable
- change one entity field
- play one sound
- show one screen element
- make the camera follow one explicit target

### 2. Higher-Level Orchestration Commands Are Still Good

Not every builtin command should be reduced to a tiny primitive.

Some commands are useful precisely because they orchestrate authored logic:
- `run_event`
- `run_command`
- `run_commands`

These are not the main problem.
They are composition/dispatch tools, and they can keep richer call context where needed.

### 3. Symbolic References Should Not Leak Everywhere

The user-facing authoring concepts:
- `self`
- `actor`
- `caller`

are useful and should remain available where they make sense.

But primitive engine commands should not all be responsible for resolving these symbols themselves.

Preferred direction:
- resolve symbols before a primitive command is invoked
- or keep symbolic resolution only in higher-level orchestration layers

### 4. The Engine Can Keep Internal Runtime Plumbing

The engine still needs access to live runtime services:
- world
- area
- persistence
- camera
- renderer/screen services
- audio
- input plumbing

So some internal runtime service object is still expected to exist.

What should change is:
- primitive commands should not effectively depend on the whole service bag as part of their public contract

## Current Problem

The current system uses one shared `CommandContext` service bag and a broad callable shape:

- runner chooses a command by `type`
- registry calls the Python implementation
- command receives `context` plus command params

This is convenient internally, but it has encouraged primitive command signatures to become too broad.

Examples of the current smell:
- commands that accept `scope`
- commands that accept `entity_id` plus `source_entity_id` plus `actor_entity_id` plus `caller_entity_id`
- commands that both resolve symbolic targets and perform a low-level mutation

## Target Shape

### Primitive Commands

Primitive commands should be split into narrow, explicit forms.

Examples of the intended direction:
- `set_world_var(name, value, persistent=false)`
- `set_entity_var(entity_id, name, value, persistent=false)`
- `add_world_var(name, amount, persistent=false)`
- `add_entity_var(entity_id, name, amount, persistent=false)`
- `check_world_var(name, op, value, then, else)`
- `check_entity_var(entity_id, name, op, value, then, else)`
- `set_entity_field(entity_id, field_name, value, persistent=false)`

The important idea is not these exact names.
The important idea is that the commands are narrow and explicit.

### Higher-Level Commands

These likely remain higher-level:
- `run_event`
- `run_command`
- `run_commands`
- other dispatch/composition commands

These commands can still:
- pass runtime context
- preserve `actor` / `caller`
- invoke other command chains

### Internal Engine Dependencies

The engine should move toward command-specific dependency injection.

Meaning:
- the engine still has full runtime state internally
- each primitive command should only receive the runtime services it actually needs

Examples:
- entity-variable mutation needs world access and maybe persistence
- camera commands need camera and maybe world
- audio commands need audio player
- screen element commands need screen manager and maybe text renderer

## Proposed Refactor Areas

### 1. Classify Current Builtins

Sort the existing builtin commands into categories:

- true primitive engine commands
- higher-level orchestration commands
- convenience wrappers that may need redesign or removal

This classification should happen before the cleanup so that we do not try to force every command into the same shape.

### 2. Narrow Variable Commands

Current broad commands in this family should be redesigned first:
- `set_var`
- `increment_var`
- `check_var`
- related variable/collection helpers

This is likely the biggest win because this family currently carries too much generic targeting/context behavior.

### 3. Narrow Entity-Field Commands

Commands like field mutation should stop accepting more symbolic/runtime targeting context than they truly need.

### 4. Review Camera Commands

Camera commands should also be checked under the same principle:
- clear explicit target/policy inputs
- only the runtime services actually needed

### 5. Review Screen/UI Commands

Screen element commands should be checked too, especially if they currently inherit more runtime context than necessary.

### 6. Keep Orchestration Commands Rich Where Appropriate

Do not accidentally cripple:
- `run_event`
- `run_command`
- generic command composition

These are part of the authored composition model and may legitimately carry richer call context.

## Migration Strategy

### Stage 1. Command Classification

Create a command inventory that marks:
- primitive
- orchestration
- transitional/problematic

### Stage 2. Introduce Explicit Primitive Replacements

Add the explicit primitive forms first.

Do not immediately remove the older broad versions until the new path is proven.

### Stage 3. Migrate Project Content And Higher-Level Builtins

Update:
- authored sample content
- higher-level builtins
- project commands

so they call the new primitive forms.

### Stage 4. Reduce Broad Primitive Surfaces

After migration:
- remove or reject the older broad primitive forms
- keep only the higher-level commands that truly need richer orchestration semantics

### Stage 5. Update Permanent Docs

Once the system is actually implemented:
- update the permanent docs
- remove this temporary file

## Things We Should Preserve

The cleanup should not remove the useful parts of the authoring model:
- entity events
- named reusable command chains
- `self` / `actor` / `caller` as meaningful authored concepts
- command composition

The goal is not to make the system weaker.
The goal is to make primitive engine operations cleaner and better separated from orchestration logic.

## Open Questions

These are not blockers to the direction, but they are not fully settled yet.

### 1. Exact Final Primitive Command Naming

The direction is clear, but the exact naming scheme is still open.

### 2. Exact Resolution Layer For `self` / `actor` / `caller`

We know primitive commands should not all resolve them directly.
What is still open is whether the final resolution happens:
- entirely in orchestration commands
- in a separate pre-resolution layer
- or through a mixed model

### 3. How Strict Dependency Injection Should Be

We agree that primitive commands should receive only the services they need.
The exact implementation shape is still open.

### 4. Which Current Builtins Count As High-Level Enough To Keep Rich Context

`run_event` and `run_command` clearly do.
Some others may still need classification.

## Working Rule For This Plan

This file is not permanent truth.

If implementation reveals that part of this plan is wrong or incomplete, the fix is:
- update the plan deliberately
- do not silently drift

And once the work is complete, this file should be removed and the permanent docs should become the source of truth.
