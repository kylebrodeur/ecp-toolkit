# ecp-toolkit

> The AI ECP control plane: one operator CLI (`ecp`) that mounts the
> family's kit repos through per-repo command manifests, vendors tag-pinned
> copies into consumer projects, and guards the vendor boundary.

**Start with [docs/quickstart.md](docs/quickstart.md)**: from nothing to a
mounted fleet. Day-to-day operation: [docs/how-to.md](docs/how-to.md).
The full command surface and every error string with its fix:
[docs/RUNBOOK.md](docs/RUNBOOK.md).

## Install

```bash
uv tool install ecp-toolkit
ecp --help
```

Until the first registry wave, install from a checkout:

```bash
uv tool install --from <path-to-ecp-toolkit> ecp-toolkit
# or run without installing:
uv run --project <path-to-ecp-toolkit> ecp --help
```

## What `ecp` does

```bash
ecp setup                      # write the config file (one section per kit, mode 600)
ecp doctor                     # which kits are present and what each declares
ecp catalog                    # print the kit catalog
ecp status                     # per-kit version, CI state, and hook state
ecp init <project>             # scaffold a consumer project: vendor/ + overlays/
ecp pull <kit> --tag <t>       # vendor a tag-pinned copy into the project
ecp vendor check               # drift guard: refuse a drifted vendor tree
ecp <kit> ...                  # one group per kit that ships a manifest
```

The kit groups are mounted, never hard-coded: each kit repo ships an
`ecp-commands.toml` declaring the commands `ecp <kit>` offers (or a
whole-surface `[passthrough]` when the kit owns its own CLI). Adding a
command is a repo-side TOML edit; `ecp` never grows a per-kit wrapper.

## The two modes

| Mode | Kit code is read from | Config source |
|---|---|---|
| In a consumer project | `<project>/vendor/<kit>/` | the project record |
| Fleet mode | the checkout under `repos.root` | the operator config file |

A consumer project never falls back to a shared checkout: the pinned tag
must be the thing that runs.

## Tests

77 contract tests, no network, no kit checkouts needed:

```bash
uv run pytest tests -q
```

## The skill

`ecp-toolkit` ships one skill teaching this repo's boundary:

```bash
# the agentskills.io SKILL.md, in this repo
skills/ecp-toolkit/SKILL.md
```

## Family

This repo is a member of the AI Engineering Control Plane (AI ECP)
family: independent kit repos whose rules are executable. Siblings:
[repo-guards](https://github.com/kylebrodeur/repo-guards) (`guv`, the
governance kit), [actions-runner](https://github.com/kylebrodeur/actions-runner)
(`arun`, the local agent-pipeline runner), and
[omp-rpc-cli](https://github.com/kylebrodeur/omp-rpc-cli) (persistent
`omp` RPC sessions). The family's standard:
the family documentation standard (in the private control-plane repo).

## Status

Facts checked 2026-10-22 against the implemented surface (`ecp --help`,
`doctor`, `catalog`, `status`, `init`, `pull`, `vendor check`, and the
manifest mount all observed live). Not yet published to a package
registry: install from a checkout or a vendored copy until the release
wave lands.