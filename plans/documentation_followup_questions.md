# Documentation Follow-Up Questions

Status: active note from the 2026-04-08 code-backed docs audit.

These are not confirmed bugs. They are implementation/documentation ambiguities
that likely need an explicit design call later.

## 1. Dialogue Discovery Convention vs Generic Project JSON

Observed implementation:

- ordinary project-relative JSON can live anywhere and still be loaded through
  `$json_file`
- startup command auditing and extra dialogue/static-reference scanning
  currently walk the conventional `project_root/dialogues/` tree specifically

Question:

- should that convention remain intentional and user-facing, or should the
  startup/audit path eventually generalize beyond `dialogues/`?

Why this matters:

- it affects how strongly the docs should recommend `dialogues/`
- it affects whether non-conventional dialogue storage should be treated as
  supported, merely possible, or something to discourage

## 2. Dialogue UI Presets vs Inventory UI Presets

Observed implementation:

- inventory UI presets are merged onto engine defaults
- dialogue UI presets currently resolve a named preset directly, with legacy and
  engine-default fallbacks, but without the same sparse deep-merge behavior

Question:

- is that asymmetry intentional and desirable, or should dialogue presets gain a
  similar partial-override merge model later?

Why this matters:

- it changes how exact the docs should be when describing preset authoring
- it also affects editor UX expectations for future structured preset editing

## 3. Public Documentation Scope for Validation Details

Observed implementation:

- startup validation now does meaningful command-authoring and static-reference
  checking that is useful for authors, contributors, and coding agents

Question:

- should more of that detail move into the canonical long-form docs
  (`AUTHORING_GUIDE.md` / `ENGINE_JSON_INTERFACE.md`), or is the docs site plus
  onboarding material the right level for now?

Why this matters:

- it affects where future validation changes must be documented first
