---
name: ecp-boundary
description: Use when working with AI ECP repos, vendored copies, or a consumer project that uses the ecp control plane: when to vendor, what may be edited, where decisions belong, and why a kit checkout is source rather than a target.
---

# The ECP boundary: source, vendor, overlay

Three rules decide every action in the AI ECP. Everything else is detail.

## 1. A repo is SOURCE, never a target

A repo is the origin of code. You read it, you clone it, you vendor it.
You never run it in place on behalf of a consumer project, and you never
edit a consumer's copy of it.

Why: a checkout carries a fixed identity. Two projects vendoring the same
repos from the same checkout share state, and one project's changes silently
become the other's. A checkout that gets edited in place stops being
reproducible, and nobody can tell which copy is authoritative.

## 2. A vendored copy is never edited

A consumer's vendored copy sits at `<project>/vendor/<repo>/`, pinned to an
upstream release tag. It is read-only.

- The code lives in the vendor tree.
- The decisions live in the overlay tree, `<project>/overlays/<repo>/`:
  config, policy manifests, hooks, state.
- A change that belongs in the code belongs in an upstream release, then
  the consumer re-vendors at the new tag.

Why: a vendored copy that has local edits can no longer be compared to its
tag. The pin becomes a lie, and "which version is this?" stops having an
answer.

## 3. The upgrade unit is the release TAG

A consumer pins a repo at a tag, not at a branch and not at a commit that
someone remembered. `ecp pull <kit> --tag <t>` (re)vendors the pinned
copy. Drift is refused on every consume.

The override exists: `--allow-local-changes` deploys a drifted tree. It
prints every finding, records the override in the project state, and shows
up in `ecp doctor`. It is never the default, and it is never a quiet
choice.

## Where things live

```
<project>/
  .ecp/config.json          the project record: slug, repos, tags, state
  vendor/<repo>/             code, pinned to a tag, read-only
  vendor/<repo>/.ecp-vendor.json   provenance: repo, tag, commit
  overlays/<repo>/           decisions: config, policy, hooks, state
```

Inside a project, the control plane reads repo code from `vendor/`. A
vendored project needs no shared repos root. Outside a project, the
fleet-level commands use the operator's configured repos root.

**A consumer project never falls back to a shared checkout.** The pinned
tag is the only thing that may run.

## Secrets

Names are public. Values are never written anywhere: not in a config
file, not in a process argv, not in the vendor tree.

A value is handed over on stdin, or through an explicit mode-0600 temp
file that the operator cleans up. The op-safe repo does exactly this: it
reads a selected `op://` reference and writes the value to a mode-0600
file, printing only the path.

## What to do when something looks wrong

- A version looks wrong: do not reset, reinit, or wipe the vendor or
  overlay trees to "fix" it. Compare against the recorded tag first.
- A local edit is needed: move it to the overlay, or make it upstream and
  re-vendor.
- It is unclear where a change belongs: STOP and ask. The wrong guess
  costs a consumer a reproducibility guarantee.

## Checks

Run the vendor guard before operating on a consumer project:

```bash
ecp vendor check
```

It compares each vendored tree against its recorded tag and fails on any
difference. A clean run is the precondition for every other command.
