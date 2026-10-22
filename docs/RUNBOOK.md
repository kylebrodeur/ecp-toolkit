# RUNBOOK: the operator's reference

Everything in this runbook is verified against `ecp` 0.1.0
(`ecp_toolkit/`, Python 3.11+, stdlib only) on 2026-10-22. The tutorial
path lives in [quickstart.md](quickstart.md); repeated tasks live in
[how-to.md](how-to.md). This file is the complete surface: every
command, every config key, every error string, and the recovery
procedures.

## The full command surface

```
ecp [-h] [--project PATH] [--fleet]
    {setup,doctor,catalog,status,init,pull,vendor} ...
```

### `ecp setup [--repos-root DIR] [--kit NAME --root DIR]`

Writes the config file (default
`~/.config/ai-ecp/config.json`, mode 600). Sections merge: an existing
file's kits are kept, named kits are seeded, and the repos root is set
when passed. Prints `wrote <path> (mode 600)` and, when the repos root
is still missing, a note with the fix line.

### `ecp doctor [--json]`

Per-kit: presence and declarations, in family order. A checkout with no
manifest prints `present, ships no manifest`. A malformed manifest is a
loud error (see the error table) and the command exits; nothing is
silently skipped. Also prints recorded `allow-local-changes` overrides
when run inside a project. Exit 0; 1 when the repos root is unconfigured
or points at a missing directory.

### `ecp catalog`

The kit table: kit, lane, what it is. Read-only.

### `ecp status [--no-net]`

One row per kit: version (from the checkout's `pyproject.toml`), local
CI state, and hook state (`git config core.hooksPath`, or `-`). Absent
kits print `absent`. Missing facts degrade to `-`; the command never
probes a network in this skeleton and never writes.

### `ecp init [<project-id>] [--dir DIR]`

Scaffolds a consumer project: `.ecp/config.json` (the record),
`vendor/`, `overlays/`, and a project `.gitignore` ignoring `vendor/`.
Bare (no id): the current directory becomes the project. Refuses to
overwrite an existing record (exit 1, `already a project`).

### `ecp pull <kit> --tag <t> [--allow-local-changes]`

The ONE command that writes to a consumer project. Order: refuse drift
first, resolve the tag before any write, clone when the vendored copy
does not exist yet (from `https://github.com/kylebrodeur/<kit>` or the
`ECP_<KIT>_REPO_URL` override), detach at the tag's commit, write
`vendor/<kit>/.ecp-vendor.json` provenance (repo, tag, commit), and
merge the record entry. Prints `vendored <kit>: <path> at <tag>`.

### `ecp vendor check [<kit>]`

The drift guard. Clean means: worktree clean apart from the managed
`.ecp-vendor.json`, HEAD equals the provenance commit, and the recorded
tag resolves to that commit. Findings name the file and where the
change belongs. Exit 0 clean, 1 drifted. Without a kit argument, every
recorded kit is checked, plus vendored trees missing from the record.

### `ecp <kit> ...` (manifest-mounted groups)

One group per kit whose checkout (fleet mode) or vendored copy (project
mode) ships `ecp-commands.toml`. Declared commands dispatch by run
kind; a whole-surface `[passthrough]` group forwards argv verbatim to
the kit's own CLI. Only fleet mode is mounted in this skeleton's
parser; a project's vendored manifests mount when the project's vendor
tree is the mode source (the executor resolves the checkout per mode).

## The config file

| Key | Meaning |
|---|---|
| `kits.<name>.root` | the kit checkout's path (or `ECP_<KIT>_ROOT`) |
| `repos.root` | the parent dir holding the kit repos (or `ECP_REPOS_ROOT`) |
| `ECP_CONFIG` | relocates the whole config file |
| `ECP_<KIT>_REPO_URL` | a pull-time clone URL override (a fork, a mirror, a local bare repo) |

Precedence: env var first, then the config file. Every field is
overridable by environment variable by design. The file holds roots and
NAMES only; never a secret value. Written mode 600.

## Manifest shape (`ecp-commands.toml`, per kit repo)

```toml
[defaults]                      # optional; merges into every [[command]]
kind = "shell"
requires = ["root"]

[[command]]
name = "read"                   # required, non-empty
summary = "what it does"        # required, non-empty
kind = "shell"                  # required; shell | python | probe
argv = ["scripts/tool.sh"]      # required non-empty for shell/python
requires = ["account"]          # config keys, enforced at run time
timeout = 30                    # optional, integer seconds
passthrough = true              # optional, boolean; forwards extra args

[passthrough]                   # whole-surface shape (alternative to [[command]])
summary = "the kit's own CLI"
argv = ["guv"]
```

A manifest declares EITHER `[[command]]` entries OR a `[passthrough]`
table, never both and never neither. The run-kind vocabulary is closed:
`shell`, `python`, `probe`. A `[passthrough]` table is a shape, not a
kind.

## Modes (the two, which never mix)

| Mode | Kit code is read from | Config source |
|---|---|---|
| In a consumer project | `<project>/vendor/<kit>/` | the project record |
| Fleet mode | the checkout under `repos.root` | the operator config file |

Selection: `--project PATH` or a current directory holding
`.ecp/config.json` selects project mode; `--fleet` selects fleet mode
even from inside a project. Outside a project, fleet mode is the only
mode. A consumer project never falls back to a shared checkout.

## Every error string, with its fix

| Error string | Emitted by | The fix |
|---|---|---|
| `no repos root configured. Fix with EITHER: ecp setup --repos-root ... / export ECP_REPOS_ROOT=...` | `doctor`, `status` | run one of the two printed fix lines |
| `the configured repos root <path> is not a directory.` | `doctor`, `status`, fleet-mode groups | correct the path or unset `ECP_REPOS_ROOT` |
| `<kit> is not vendored in this project (<path>); fix: run `ecp pull <kit> --tag <release>` first` | executor, project mode | vendor the kit into the project |
| `invalid command manifest <file>: <message>` | the loader, at parse/mount time | fix the named file in the named kit's repo; never weaken the loader |
| `unknown kit <name>; known kits: ...` | `pull` | use a catalogued kit name, or point `ECP_<KIT>_REPO_URL` at the kit's real repo |
| `missing a --tag: the upgrade unit is the release tag, so every pull names one` | `pull` | pass `--tag <release>` |
| `git clone failed for <kit>: <output>` | `pull` | fix the URL (network, permissions, or `ECP_<KIT>_REPO_URL`) |
| `tag <t> not found upstream for <kit>` | `pull` | use a tag that exists upstream (`git ls-remote --tags <url>`) |
| `<kit>'s vendored tree has local changes; refusing. Findings: ...` | `pull` | resolve the findings, or pass `--allow-local-changes` deliberately |
| `<this dir> is not a project. Fix: run `ecp init` here first` | project-record reads | run `ecp init`, or pass `--project <path>` |
| `<record> already exists; this directory is already a project` | `init` | the project exists; work in it |
| `project id <id> cannot form a project directory or app name.` | `init` | lowercase letters, digits, dots, dashes, underscores |
| `<kit> is not configured: missing <keys>. Fix with EITHER: ...` | the config gate | export the named env var(s) or run `ecp setup` |
| `config <path> is not valid JSON: <exc>` | config load | repair or remove the file, then `ecp setup` |
| `<kit>: <argv0> is not available on PATH` | executor | install the tool the command declares (`uv` for the `python` kind) |
| `vendor check: DRIFTED (findings above)` | `vendor check` | work the findings: overlay the change or re-vendor at the same tag |

Also: argparse usage errors exit 2 (`unrecognized arguments:`), and the
unrecognized-args error is the DESIGN, not a bug: only a passthrough
command forwards extra arguments.

## Recovery procedures

### A vendored tree is drifted and the project must run NOW

Do not override reflexively. Read the findings; each names where the
change belongs. If the change is the consumer's decision, it belongs in
`overlays/<kit>/`: move it, then refresh:

```bash
mv vendor/<kit>/the-edit overlays/<kit>/
ecp pull <kit> --tag <the-same-tag>
ecp vendor check
```

### The vendor copy was deleted or half-deleted

```bash
ecp pull <kit> --tag <the-recorded-tag>
ecp vendor check
```

The record (`<project>/.ecp/config.json`) still names the tag; the pull
re-creates and re-pins the tree.

### The config file drifted or was hand-edited into nonsense

```
config <path> is not valid JSON: ...
```

Fix or remove the file, then re-run `ecp setup --repos-root ...`. A
missing env-named file (`ECP_CONFIG`) fails named as well.

### A kit's manifest broke and every ecp invocation errors

The loader fails closed BY DESIGN: a broken manifest is a loud error,
never a silently missing group. The error names the file; fix it in the
kit's own repo (it is that repo's edit, not a consumer edit):

```
invalid command manifest /path/to/kit/ecp-commands.toml: command 'x' has
unknown kind 'teleport'; supported: ['shell', 'python', 'probe']
```

### A pull cloned from the wrong place

`ECP_<KIT>_REPO_URL` overrides the clone URL per call:

```bash
export ECP_REPO_GUARDS_REPO_URL=/path/to/local-bare-repo.git
ecp pull repo-guards --tag v0.1.0
```

The tag pin is unaffected: whatever the URL, the checkout detaches at
the tag's commit and the provenance records the commit.

## Library surface (for scripts that need the pieces)

```python
from ecp_toolkit import config, manifest, project

loaded = manifest.load(pathlib.Path("repo-guards"))   # Manifest | None
config.require("repo-guards", ("root",))              # the exact-fix gate
ok, findings = project.vendor_check(root, "repo-guards")
```

Every guard is a pure function over its inputs (paths, config, a git
runner); the CLI prints, the functions return.

## Verification of this repo's own docs

```bash
uv run pytest tests -q
uv run ruff check .
uv run pytest tests -q
uv run ruff check .
uv run ecp --help
```

Expected: every `ecp-toolkit:` check PASS, `77 passed`, lint clean, and
the usage block shown in the quickstart.