# Docs Maintenance

This docs site should stay aligned with the repo's existing documentation truth model instead of creating a second drifting truth.

## Documentation Roles

### Canonical contract docs

These must stay close to implementation reality:

- `ENGINE_JSON_INTERFACE.md`
- `AUTHORING_GUIDE.md`
- `README.md`
- editor current-state docs such as `tools/area_editor/README.md`

### Explanatory docs

These explain boundaries, direction, and architecture:

- `PROJECT_SPIRIT.md`
- `architecture.md`
- `tools/area_editor/ARCHITECTURE.md`

### Planning docs

These describe intended or future work and should not silently become current truth:

- `plans/`
- `roadmap.md`
- `tools/area_editor/ROADMAP.md`
- `tools/area_editor/FUTURE_FEATURES.md`

## Update Order

When implementation changes:

1. update the relevant plan if the intended design changed
2. change the implementation
3. update canonical contract and reference docs
4. update author-facing workflow docs
5. update summary docs
6. update `CHANGELOG.md`

## This Site's Role

The MkDocs site is the curated front door. It should:

- help people find the right concepts quickly
- summarize and organize existing knowledge
- point clearly to canonical deep references
- avoid inventing parallel terminology or contradictory contracts

## When To Update Which Docs

If the JSON contract changes, review:

- `ENGINE_JSON_INTERFACE.md`
- `AUTHORING_GUIDE.md`
- this site's reference pages
- `README.md`
- `CHANGELOG.md`

If command behavior changes, review:

- `ENGINE_JSON_INTERFACE.md`
- `AUTHORING_GUIDE.md`
- this site's command pages
- `README.md`
- `CHANGELOG.md`

If editor workflows change, review:

- `tools/area_editor/README.md`
- `tools/area_editor/ARCHITECTURE.md`
- this site's editor pages
- `README.md`
- `CHANGELOG.md`

## Anti-Patterns To Avoid

- copying a plan into the docs site as if it were shipped behavior
- leaving old limitations in docs after the editor or runtime has moved forward
- documenting only tests while skipping real project validation expectations
- making the docs site nicer but less truthful than the repo docs

## Best Practice

When in doubt, update the canonical repo doc first, then make the docs site explain that updated truth more clearly.
