# ecp-toolkit: the agent boundary (`ecp`)

`ecp` is the AI ECP control plane: it mounts kit repos through per-repo
command manifests, vendors tag-pinned copies into consumer projects, and
guards the vendor boundary. This file is the boundary an agent obeys when
operating it; the tutorial prose lives in
[docs/quickstart.md](docs/quickstart.md) and
[docs/how-to.md](docs/how-to.md).

## The boundary

1. **The control plane mounts, it does not hard-code.** Adding a command
   is a TOML edit in the kit's own `ecp-commands.toml`. NEVER add a
   per-kit wrapper to the `ecp` source; that reintroduces the problem the
   manifest design exists to remove.
2. **A vendored copy is never edited.** Consumer changes land in
   `overlays/<kit>/`. A code fix belongs in an upstream release, then the
   consumer re-vendors at the new tag. `ecp vendor check` refuses drift;
   treat its findings as evidence, not noise.
3. **The upgrade unit is the release TAG.** `ecp pull <kit> --tag <t>`
   pins the copy. A pull without a tag is refused; never vendor at a
   branch or a commit someone remembered.
4. **The two modes never mix.** Inside a consumer project, kit code is
   read from and run in `vendor/<kit>/`. NEVER point a consumer project
   at a shared checkout to "make it work"; that breaks the pin, and the
   pinned tag stops being what actually runs.
5. **`--allow-local-changes` is never the default.** It prints every
   finding, records the override in the project state, and shows up in
   `ecp doctor`. A drifted tree that "just needs to run" is a state to
   fix, not to override casually.
6. **Fail closed on manifests.** A malformed manifest is an error naming
   the manifest and the problem. NEVER weaken the loader's validation to
   keep a broken kit mounting; fix the manifest in the kit's repo.
7. **The fleet view is read-only.** `ecp status`, `ecp doctor`, and
   `ecp catalog` report; they never write to a member repo. Deep kit
   work stays in the kit's own CLI (through the mounted group or the kit
   repo itself).
8. **Secrets are names only.** A kit manifest declares the NAMES it
   needs; a value arrives on stdin or through an explicit mode-0600 temp
   file. NEVER put a secret value in a config file, a process argv, or
   the vendor tree, including through this CLI's own config.
9. **The config file is mode 600 and holds roots and names.** `$ECP_CONFIG`
   relocates it; `ECP_<KIT>_ROOT` overrides one kit's root. An operator
   override should never require editing a config file.

## What this kit is NOT

- NOT a kit. It reimplements nothing a kit owns: a kit that ships a
  full CLI mounts as a `[passthrough]` group and `ecp` delegates argv
  verbatim.
- NOT a config store for secrets. Its config holds roots, names, and
  flags; never values.
- NOT a release tool. Releasing a kit follows the family's release
  model in the kit's own repo; `ecp` vendors releases, it does not cut
  them.
- NOT a fallback runner for an unvendored kit. A consumer project with
  no vendored copy of a kit does not get a shared-checkout rescue.

## When an agent is asked to extend the fleet

A new kit is: a repo, its `ecp-commands.toml` (or the decision to ship
none and mount nothing), and its checkout under the operator's repos
root. No `ecp` source change. Verify with:

```bash
ecp doctor
```

The kit's row appears with what it declares, or "ships no manifest" when
it deliberately mounts nothing.