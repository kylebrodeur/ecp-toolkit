---
name: ecp-toolkit
description: Use when operating a consumer project through the ecp control plane (init, pull, vendor check, or a mounted kit command), when a manifest fails to load, or when deciding whether a change belongs in the vendor tree, the overlay, or an upstream release.
---

# Operating `ecp` (the AI ECP control plane)

`ecp` mounts the family's kit repos. Each kit repo ships an
`ecp-commands.toml`; the CLI offers exactly what the manifests declare,
plus the fleet-level verbs. Install it with:

```bash
uv tool install --from "git+https://github.com/kylebrodeur/ecp-toolkit@v0.1.0" ecp-toolkit
```

The PyPI entry is DECIDED and PENDING, so the route above is the one
that works today. A bare `uv tool install ecp-toolkit` fails: there is
no such package on PyPI.

## The commands

```bash
ecp setup --repos-root ~/repos        # once: config file, mode 600
ecp doctor                            # presence + declarations, per kit
ecp catalog                           # the family's kit table
ecp status                            # per-kit version, CI, hook state
ecp init my-project                   # scaffold: .ecp/, vendor/, overlays/
cd my-project
ecp pull repo-guards --tag v0.1.0     # vendor a tag-pinned copy
ecp vendor check                      # refuse a drifted vendor tree
ecp repo-guards check .               # a mounted kit command (passthrough)
```

## The rules an agent obeys

1. **Vendor is code, overlay is decisions.** A change to how a kit RUNS
   in one project goes in `overlays/<kit>/`. A change to the kit itself
   goes upstream, then `ecp pull <kit> --tag <new-tag>` re-vendors.
   Never edit `vendor/<kit>/`.
2. **Every pull names a tag.** The pull refuses without one. The pin is
   the guarantee; a branch pin is a lie waiting to happen.
3. **Drift is refused; the override is explicit.** `--allow-local-changes`
   records itself in the project state and prints every finding. It is
   never a default and never a quiet choice.
4. **Modes never mix.** Inside a project, commands run the vendored copy
   even when a shared checkout sits configured and reachable. Outside a
   project, commands run the checkout under `repos.root`.
5. **Mounts come from manifests.** A kit's surface changes when the kit
   edits its manifest, not when `ecp` ships code. A malformed manifest
   is an error naming the manifest and the problem; fix the manifest,
   never the loader.
6. **Names only.** `ecp` handles secret NAMES (the `requires` gate) and
   never values.

## Reading a failure

- "not a consumer project": run `ecp init` first, or pass `--project`.
- "is not vendored in this project": run `ecp pull <kit> --tag <release>`.
- "invalid command manifest <path>: <message>": fix the named file in
  the named kit's repo. The mount fails closed, by design.
- "<kit> is not configured: missing <keys>": set the keys (env override
  or `ecp setup`); the message carries both fix lines.

## Not this CLI's job

- It does not reimplement a kit's CLI (passthrough delegates verbatim).
- It does not cut releases or own kit state; the fleet view is
  read-only.
- It never stores or transmits a secret value.

## The family rule this mounts

Source, vendor, overlay: the three rules that decide every action are
the `ecp-boundary` skill (the system repo's `skills/ecp-boundary/`).
This repo's CLI is the mechanical form of those rules.