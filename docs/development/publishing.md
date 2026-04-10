# Publishing

This docs site is designed to live inside the repo and publish as a static site.

## Local Workflow

Install docs dependencies:

```bash
pip install -r requirements-docs.txt
```

Preview locally:

```bash
mkdocs serve
```

Build the static site:

```bash
mkdocs build
```

Generated output goes to `site/`, which is gitignored.

## Recommended Hosting Options

### GitHub Pages

This is the simplest default if the repo stays on GitHub.

Why it fits:

- docs live with the repo
- the site is static
- deploys can happen from the same repository
- custom domains are supported later

### Read the Docs

This is a strong choice if the docs become a more serious standalone product surface and you want:

- hosted docs infrastructure
- Git-based updates
- versioned docs
- docs-focused hosting rather than general static hosting

### Netlify or Cloudflare Pages

These are also good fits if you want:

- static hosting
- branch or preview deploy workflows
- flexible custom-domain handling

## Practical Recommendation For This Repo

Start with GitHub Pages unless there is a strong reason not to. It keeps the setup simple while the docs structure is still settling.

## Current Automation

The repo now includes a GitHub Actions workflow that installs the docs dependencies and runs:

```bash
mkdocs build --strict
```

That gives doc changes a real build check on pushes and pull requests.

## Useful Next Automation Step

When you are ready to publish publicly, add one of:

- a GitHub Pages deployment workflow
- a Read the Docs project configuration
- a Netlify or Cloudflare Pages deployment

## Maintenance Reminder

Publishing only helps if the docs are trustworthy. The highest-value habit is still keeping the repo's canonical docs and validation steps aligned with the code.
