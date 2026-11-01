---
name: ecp-release
description: Use when judging whether an AI ECP kit release is actually published, or when reading one release's notes against another's: the four artifacts that make a tag published, and the tag-without-release failure to recognize.
---

# What makes an ECP release published

A release is a tag you can install and a body you can read, with the
source notes behind them. The family keeps release WRITING in its private
control-plane repo; a reader verifies the published result.

## Four artifacts make a release published

All four must exist before anyone calls a release "published":

1. An annotated tag on the default branch (`vX.Y.Z`).
2. A GitHub release object with a real notes body.
3. Source notes kept by the family (the private control-plane repo).
4. The kit's own version equal to the tag (package.json / pyproject).

A body that does not match its source note, a tag with no release object,
a package version that disagrees with the tag: each is a half-published
state, not a release.

## The failure to recognize

A tag pushed without its release object is an incomplete state that only
widens: the tag exists, callers pin it, and the notes never materialize.
Callers believe they have a release. They do not. This was caught live in
a sibling family: a version existed as a tag-only "release" for two
hours.

**For a reader:** a tag resolves, the release page opens, the body
explains the change, and the kit's version matches. Any of the four
missing is worth a report, not a workaround.

## Reading a release

- The notes state what changed, the public surface, the verification,
  and the upgrade notes (concrete commands and file paths, not
  adjectives).
- A docs-only release says "docs patch; no code changes".
- A body is never silently rewritten after publication: a fix publishes
  a NEW version's note that names what the earlier one got wrong.

## Upgrading from it

The move is [the ecp-upgrade skill](../ecp-upgrade/SKILL.md): pin to the
exact tag, reinstall over the old install, preflight the old state.
