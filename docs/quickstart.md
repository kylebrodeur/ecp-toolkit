# Quickstart: from nothing to a mounted fleet

Checked against `ecp` 0.1.0 on 2026-10-22. Every command is real; every
output shown is real output from the commands above it.

You need: Python 3.11 or newer and `uv` (`git` for the vendor flow).

## 1. Get the CLI

The CLI is not published to a package registry yet. The registry entry
is DECIDED and PENDING; the route below is the one that works today.

```bash
uv tool install --from "git+https://github.com/kylebrodeur/ecp-toolkit@v0.1.0" ecp-toolkit
# or run without installing:
uv run --project /path/to/ecp-toolkit ecp --help
```

The install names the **package** (`ecp-toolkit`), not the console
script (`ecp`); `uv` rejects the script name, because the two are
different things. A bare `uv tool install ecp-toolkit` fails, because
there is no such package on PyPI.

Expected output (the same surface for both forms, `--help` observed live):

```
usage: ecp [-h] [--project PATH] [--fleet]
           {setup,doctor,catalog,status,init,pull,vendor} ...

The AI ECP control plane: fleet commands plus one group per kit that ships a
manifest

positional arguments:
  {setup,doctor,catalog,status,init,pull,vendor}
    setup               write the config file (one section per kit, mode 600)
    doctor              which kits are present and what each declares
    catalog             print the kit catalog
    status              per-kit version, CI state, and hook state (read-only)
    init                scaffold a consumer project (record, vendor/,
                        overlays/)
    pull                vendor a tag-pinned copy of ONE kit into this project
    vendor              the vendored-copy guards

options:
  -h, --help            show this help message and exit
  --project PATH        operate inside the consumer project at PATH (reads
                        vendor/<kit>/, never a shared checkout)
  --fleet               force fleet mode even from inside a project directory
                        (the mode separator)
```

## 2. Write the config

```bash
ecp setup --repos-root ~/repos   # the parent dir holding the kit repos
```

Expected output:

```
wrote /Users/you/.config/ai-ecp/config.json (mode 600)
```

The file holds one section per kit plus the repos root. `ECP_CONFIG`
relocates it; `ECP_<KIT>_ROOT` (for example `ECP_REPO_GUARDS_ROOT`)
overrides one kit's root without editing the file.

## 3. Meet the fleet

```bash
ecp doctor
```

Expected output on a workspace where no kit is checked out yet (the
absence is reported, never hidden):

```
repos root: /Users/you/repos
  ecp-toolkit: absent (not checked out under /Users/you/repos)
  repo-guards: absent (not checked out under /Users/you/repos)
  ...
```

When a kit checkout ships an `ecp-commands.toml`, its row names what it
declares:

```
  repo-guards: passthrough -> ['guv'] (the kit's own CLI)
  op-safe: read, health
```

A kit present with no manifest prints
`present, ships no manifest (mounts nothing; a kit may ship no manifest)`.

The catalog table:

```bash
ecp catalog
```

## 4. Scaffold a consumer project

```bash
ecp init demo-project
```

Expected output:

```
initialized project /Users/you/demo-project
next:
  ecp pull <kit> --tag <release>     # vendor a kit, pinned to a tag
  ecp vendor check                   # refuse a drifted vendor tree
```

The layout is one layout:

```
demo-project/
  .ecp/config.json    the project record
  vendor/             tag-pinned kit copies (never edited)
  overlays/           your decisions: config, hooks, state
```

`ecp init` again in the same project refuses:
`already exists; this directory is already a project`.

## 5. Vendor a kit, pinned to a tag

```bash
cd demo-project
ecp pull repo-guards --tag v0.1.0
```

Expected output (on success):

```
vendored repo-guards: /Users/you/demo-project/vendor/repo-guards at v0.1.0
```

Two refusals you will meet early:

```
error: missing a --tag: the upgrade unit is the release tag, so every pull names one
```

(the `--tag` is required; a branch pin is not accepted) and, on an
unknown kit:

```
error: unknown kit 'nope'; known kits: ecp-toolkit, repo-guards, ...
```

A kit not yet published upstream points the pull at a fork, mirror, or
local bare repo with `ECP_<KIT>_REPO_URL` (for example
`ECP_OP_SAFE_REPO_URL`); the tag pin still applies.

## 6. Run a mounted kit command

Once the kit's vendored copy ships a manifest, its group mounts:

```bash
ecp repo-guards check .        # passthrough: forwards argv verbatim to guv
```

Inside a project the command runs the VENDORED copy, and the project
needs no repos root at all. Outside a project (fleet mode) it runs the
checkout under `repos.root`. The two modes never mix.

## 7. Guard the vendor boundary

```bash
ecp vendor check
```

Expected on a clean tree:

```
vendor check: ok
```

Edit a vendored file in place (the mistake) and run it again:

```
vendored copy is modified: kit-file.md - vendor/ is not a scratch tree;
changes belong in overlays/repo-guards/ or in an upstream release
vendor check: DRIFTED (findings above)
```

Exit code 0 is clean; 1 is drifted. The full runnable walkthrough (kit
repo, project, pull, mounted command, a drift, and the refusal) is
[examples/vendor-guard-demo.py](../examples/vendor-guard-demo.py):
`uv run python examples/vendor-guard-demo.py`.

## Where to go next

Day-to-day operation (the tasks you repeat):
[docs/how-to.md](how-to.md). The full command surface, every error
string, and the recovery procedures: [docs/RUNBOOK.md](RUNBOOK.md).
The boundary rules (what may be edited, where decisions belong):
[AGENTS.md](../AGENTS.md).