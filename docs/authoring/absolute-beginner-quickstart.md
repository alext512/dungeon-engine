# Absolute Beginner Quickstart

Use this page if you are completely new to this project, new to JSON, or even new to Python-based tools in general.

This page is intentionally practical. The goal is not to explain everything at once. The goal is to get you from "I opened the repo" to "I made a visible change" with the least confusion possible.

## What This Project Actually Is

This project is a game engine plus an editor.

- the engine runs the game
- the editor helps you build and change game content
- the game content mostly lives in JSON files

If "JSON" sounds scary, treat it as this:

- JSON is just a structured text file
- the engine reads those text files to know what your game contains
- rooms, entities, dialogue, items, and command chains are mostly defined in those files

When the docs say "authored JSON", they simply mean:

- JSON files that you create or edit as part of your game

## The Beginner Mental Model

For a beginner, the easiest mental model is:

1. open a project
2. use the editor for the visual and structured parts
3. save your changes
4. run the game
5. only look at raw JSON when you want more control

You do not need to understand every file before you begin.

## Your First Goal

Your first goal should be very small:

- open the sample project
- open one area
- change one visible thing
- save
- run the game and confirm the change

That gives you confidence that the workflow works.

## Step 1: Launch The Editor

If you are on Windows, start with:

```text
tools\area_editor\Run_Editor.cmd
```

That launcher is meant to be beginner-friendlier than typing commands by hand:

- if the editor environment does not exist yet, it creates one
- if the editor dependencies are missing, it installs them
- if Python is missing, it tells you that clearly

If you prefer the command line, you can still launch it from `tools/area_editor/` with:

```text
python -m area_editor
```

## Step 2: Open The Sample Project

The repo includes a sample project at:

```text
projects/new_project/project.json
```

Open that project in the editor.

If the editor starts without a project already loaded, choose the project manifest above when it asks you what to open.

## Step 3: Open One Area

A good first area to inspect is:

```text
areas/start
```

This lets you see a real authored room with tiles and placed entities.

## Step 4: Make One Small Change In The Editor

Good beginner-safe examples:

- paint a couple of tiles somewhere obvious
- move one entity by one cell
- change one render property

Do not worry yet about making something "good". The point is just to prove the workflow to yourself.

## Step 5: Save

Save your change in the editor.

What happened behind the scenes:

- the editor updated JSON files in the project
- those JSON files are the real project content
- the game will read those files the next time you run it

That is the core authoring loop of this engine.

## Step 6: Run The Game

From the repo root, you can launch the sample project with:

```text
Run_Game.cmd --project projects/new_project
```

Or:

```text
python run_game.py --project projects/new_project
```

If your change was in `areas/start`, you can also jump straight there:

```text
python run_game.py --project projects/new_project areas/start
```

## What "Authoring" Means Here

In this project, "authoring" mostly means:

- making or editing rooms
- placing entities
- choosing templates
- wiring interactions
- editing dialogue
- adjusting project data

Some of that happens in the editor.
Some of that happens in JSON files directly.

The editor is the main path.
Raw JSON is the fallback path when you need more power or a surface the editor does not cover yet.

## What The Important Files Are

You do not need to memorize these yet, but this is the beginner map:

- `project.json`
  - the project's main manifest
- `areas/`
  - the rooms or maps
- `entity_templates/`
  - reusable definitions such as players, switches, gates, or props
- `dialogues/`
  - dialogue and menu data
- `commands/`
  - reusable command chains
- `items/`
  - item definitions
- `assets/`
  - images, fonts, and other art assets

## When To Use The Editor vs Raw JSON

Use the editor first when you want to:

- edit an area visually
- place or move entities
- adjust project-level structured data
- browse content safely

Use raw JSON when you want to:

- make deeper command changes
- edit a field the structured UI does not expose yet
- copy or compare exact data more directly

## If You Feel Lost

That is normal. The easiest recovery path is:

1. go back to the sample project
2. inspect one area and one entity template
3. make one tiny change
4. run again

You do not need to understand the whole engine before you can use it.

## Where To Go Next

- [Install and Run](install-and-run.md) for the practical launch commands
- [Editor Overview](editor/index.md) for what the editor can do today
- [Authoring Workflow](authoring-workflow.md) for the normal project-building path
- [Project Layout](project-layout.md) for the file/folder map
- [JSON and Command Reference](reference/index.md) when you need exact field details
