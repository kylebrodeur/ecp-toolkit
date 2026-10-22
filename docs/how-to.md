# How-to: the tasks you repeat

Checked against `ecp` 0.1.0 on 2026-10-22. One question per section.
The one-time setup lives in [quickstart.md](quickstart.md); the full
command surface and recovery procedures live in [RUNBOOK.md](RUNBOOK.md).

## How do I see what the fleet offers right now?

```bash
ecp doctor
```

One line per kit: what it declares, that it ships no manifest, or that
it is absent. `--json` emits the same view as JSON for a script. Fleet
commands are read-only; they never write to a member repo.

## How do I point one kit at a different checkout?

Without editing the config file:

```bash
export ECP_REPO_GUARDS_ROOT=/path/to/other-checkout
```

Every config field is also an environment variable (`ECP_<KIT>_ROOT`
for a kit root, `ECP_REPOS_ROOT` for the fleet root, `ECP_CONFIG` for
the config path). An operator override should never require editing the
file; that is the design's per-call override rule.

## How do I add a mounted command for a kit?

Edit the KIT's own `ecp-commands.toml` (one TOML table), never `ecp`:

```toml
[[command]]
name = "new-command"
summary = "what it does for the operator"
kind = "shell"
argv = ["scripts/new-command.sh"]
```

The next `ecp <kit> ...` invocation mounts it. The three run kinds:
`shell` (a kit script in the kit's checkout), `python` (a kit Python
entry point via `uv run python`), and `probe` (a health/presence check).
A kit that owns a full CLI declares `[passthrough]` instead, and
`ecp <kit> <anything...>` forwards argv verbatim.

## How do I check whether my project's vendor tree drifted?

```bash
ecp vendor check
```

Exit 0 is clean; exit 1 lists findings, each naming the file and where
the change belongs:

```
vendored copy is modified: hooks.sh - vendor/ is not a scratch tree;
changes belong in overlays/repo-guards/ or in an upstream release
```

One kit only: `ecp vendor check <kit>`.

## How do I move a change I made by mistake out of a vendored copy?

The finding names the file. Move the content into `overlays/<kit>/` (or
drop it if it does not belong anywhere), then restore the vendored copy:

```bash
ecp pull <kit> --tag <the-same-tag>
ecp vendor check
```

A same-tag pull is a checkout refresh: idempotent, and it re-proves the
pin. Never edit inside `vendor/` to "make it run".

## How do I upgrade a vendored kit?

The upgrade unit is the release tag:

```bash
ecp pull repo-guards --tag v0.2.0
ecp vendor check
```

Run the second command after every pull; a clean tree is the
precondition for every other command. Moving to a different tag while
the tree is drifted refuses first:

```
error: repo-guards's vendored tree has local changes; refusing. Findings:
  - vendored copy is modified: ...
Fix: re-vendor over it after deciding, or pass --allow-local-changes
(the explicit, recorded override)
```

## When is --allow-local-changes acceptable?

Only deliberately, and it is never quiet: it prints every finding,
records the override in the project state, and the override shows up in
`ecp doctor` output (`override recorded: allow-local-changes on <kit>`).
If you cannot say why the drift is wanted, do not pass the flag; fix the
state instead.

## How do I run a kit command against a project from somewhere else?

```bash
ecp --project /path/to/demo-project repo-guards check .
```

The `--project` flag selects project mode (reads that project's
`vendor/<kit>/`); omitting it uses the current directory when it holds a
project record. `--fleet` force-selects fleet mode from inside a
project. The two modes never mix, and project mode has no fallback to a
shared checkout.

## How do I require a kit's config keys before a command runs?

A manifest command declares `requires = ["key"]`. At run time the gate
checks the kit's config section and exits with the exact fix:

```
op-safe is not configured: missing account. Fix with EITHER:
  export ECP_OP_SAFE_ACCOUNT=<value>
  ecp setup   (writes the config file at /Users/you/.config/ai-ecp/config.json)
```

Names only: the config stores keys like `account` or `root`, never
secret values.

## How does the fleet view behave in CI?

`ecp status` is safe to run in CI: it reads checkouts and git config
locally, degrades missing facts to `-`, and never probes a network in
this skeleton. Expected:

```
kit                    version    ci           hooks
ecp-toolkit            0.1.0      local        hooksPath=-
```