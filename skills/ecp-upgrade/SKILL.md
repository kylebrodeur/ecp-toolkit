---
name: ecp-upgrade
description: Use when upgrading an already-set-up repo or install to a newer AI ECP release: a kit pinned as a git dependency, a fixed-prefix global install, a vendored tag-pinned copy in a consumer, or a team manifest and local state an older version created.
---

# Upgrading an ECP repo that is already set up

The upgrade unit is the release TAG, and an upgrade is a pin-bump plus a
state check, never a re-setup. Nothing here rebuilds from nothing;
[ecp-release](../ecp-release/SKILL.md) makes the release, this one moves
what already exists onto it.

## The four setups an upgrade can meet

| Setup | Where the pin lives | The upgrade move |
|---|---|---|
| Git dependency (npm / uv tool / pnpm) | the `#vX.Y.Z` / `@vX.Y.Z` ref in the consumer's manifest or install line | Change the ref, reinstall, re-verify |
| Fixed-prefix global install | `~/.local/npm-global/lib/node_modules/<kit>/package.json` | Re-run the same `npm install --global --prefix ... "github:<kit>#v<new>"` over it |
| Vendored copy in a consumer | the vendor copy's provenance (`<vendor>/<repo>/version.txt`) | `ecp pull <repo> --tag <new>` (never edit the copy) |
| A consumer project's own repo state | its manifests, lockfiles, generated state, and hooks | The state checks below, per repo's own docs |

## The upgrade order

1. **Read the source notes for every release between the pins** (newest
   first). Tags and bodies live in the kit's own GitHub releases
   (https://github.com/kylebrodeur/<kit>/releases); the family's private
   control-plane repo keeps the source copies. The gap decides the rest:
   a note that says "no runtime change" short-circuits the state checks;
   one that names a manifest field, an error string, or a state file
   pins a concrete step below. A published note is a record: what it
   claimed is what that release did, and a later fix releases its own
   note.
2. **Bump the pin.** One unit: the tag. A semver range
   (`^0.2.0`, `>=24`-style dependency ranges) is not a pin; resolve it
   to the exact tag and record the tag in the consumer.
3. **Reinstall from the pin.** The install is re-run over the old one,
   not cleaned and recreated (a global prefix keeps other kit installs
   alive; a vendored tree keeps its overlay).
4. **Run the consumer's gates:** the repo's own test suite first
   (every public kit's docs name the commands), then any family-level
   checks that repo's docs prescribe.
5. **Run the kit's own preflight against the real state** (`teamctl
   check` for agent teams; the member's equivalent read-only mode
   otherwise). The old state must pass the new code's preflight; that
   is the compatibility test that matters.
6. **Record the move**: the consumer commit names the old and new tags.

## State that the new code must accept (the real checks)

The 2026-10-31 node-runtime release (`agent-workspace-kit` v0.2.0) is the
worked example of what an upgrade handoff must enumerate. Each item is a
thing an OLD setup created that NEW code reads or refuses:

- **Node requirement vs the RUNNING runtime.** A kit installed under an
  old Node (an nvm-version-scoped global) breaks twice: the binary
  disappears when nvm switches, and the new floor refuses the old
  runtime. Move to a fixed prefix
  (`npm install --global --prefix "$HOME/.local/npm-global`
  plus the PATH export in the shell profile), which is independent of
  the active nvm version. Verify: `node --version` first on PATH, then
  run the kit's own preflight.
- **Manifest fields the new validator knows.** New optional fields must
  be OPTIONAL: an unset field upgrades clean, a set one is validated
  (fail-closed). The upgrade check is the preflight on the UNCHANGED
  old manifest: zero new errors means compatible; any new error string
  is a handoff item with its fix.
- **Generated layout and state an old version wrote.** Old generated
  artifacts (a `.kdl` with the bare `node` as pane command, prompt
  files from stale profiles) are REGENERATED, not migrated: the write
  modes rebuild them on the next start. Nothing hand-edits old output;
  delete-and-regenerate is the migration, and it needs no data move
  when the sources (manifest, profiles) are the tracked files.
- **Local state dirs.** Session dirs and lock files owned by the old
  version keep working when their shape is unchanged; when a shape
  changes, the release notes name it and the upgrade wipes it
  (`rm -rf <team>/.agent-workspace`, the kit's own recovery path) after
  confirming nothing in it is operator data.
- **Worktrees, branches, hubs: things the old version did not create.**
  New mechanisms create new state (`git worktree add`, a tests-lock
  file, group-suffixed link names). An upgrade that turns them on
  changes peer identity and checkout layout; the notes that introduce
  them are the handoff, and switching a live team needs a stop
  (`zellij kill-session` or the lanes' `.stop` sentinels) before the
  first start under the new version.

## The compatibility contract for the family

A new release upgrades every SUPPORTED old pin with:

1. A source note whose upgrade notes are concrete commands and file
   paths, not adjectives.
2. Optional fields stay optional; unset stays valid.
3. Old generated output is never read as input; the write modes
   regenerate it.
4. Local state either keeps its shape or is named for deletion (never
   operator data).
5. The consumer's post-upgrade proof is the kit's read-only preflight
   on its real state plus the consumer's own test suite.

## The failure this prevents

An install that "worked" until the runtime moved under it: a global bin
disappeared on `nvm use`, a manifest that passed v0.1.0 but trips a new
floor, a workflow re-creating stale prompts nobody regenerated. Every one
of those is a state the upgrade handoff had to name. The check for them
is mechanical: preflight old state under new code, read the notes gap,
test the suite. Nothing trusts "it should still work".

## Rules

- The tag is the only upgrade unit; a range is not a pin.
- Upgrade = pin-bump + reinstall + preflight old state + suite, in that
  order; never re-setup.
- Regenerate, never migrate, generated artifacts.
- Never destroy local state the notes did not name.
- A handoff that cannot name the fix per finding is not done.