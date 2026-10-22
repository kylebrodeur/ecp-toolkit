# Contributing to ecp-toolkit

## The setup

The CLI is Python 3.11+, stdlib only, tooling via `uv`:

```bash
git clone https://github.com/kylebrodeur/ecp-toolkit
cd ecp-toolkit
uv sync --group dev
uv run pytest tests -q
```

Expected output:

```
.................... [100%]
77 passed in 2s (timing varies)
```

No network and no kit checkouts are needed: the tests build synthetic
kit repos in temporary directories.

## The gates (run before submitting)

```bash
uv run pytest tests -q
uv run ruff check .
```

Expected: every test green, `All checks passed!`. These are exactly what
`.github/workflows/ci.yml` runs.

## Ground rules

- **Stdlib only.** No runtime dependencies; `git` and `uv` are invoked
  as CLIs. A dependency needs a written reason, not convenience.
- **The control plane mounts, it does not hard-code.** A new kit is a
  new repo plus one manifest, with no change to the `ecp` source. Any
  change that hard-codes a kit name into the parser is the bug this
  design exists to prevent.
- **Fail closed.** A malformed manifest is an error naming the manifest
  and the problem, with a fix line, never a silently skipped command.
  Every loader validation rule carries a test that proves the rule
  fires.
- **The two modes never mix.** Inside a consumer project, kit code is
  read from and run in `vendor/<kit>/`; in fleet mode, from the checkout
  under `repos.root`. A consumer project never falls back to a shared
  checkout.
- **Secrets are names only.** No secret value is ever read, stored, or
  passed on argv by this CLI.
- **No AI slop in comments or docs.** Describe why code exists, not
  what it does. Prose carries no em/en dashes and none of the banned
  filler words.
- **Tests are contracts.** A change lands with a test that fails before
  and passes after.

## Workflow

1. Fork, create a feature branch.
2. Set up per the block above.
3. Run the repo's CI commands locally before submitting; they are
   exactly what `.github/workflows/ci.yml` runs (`pytest` + `ruff`).
4. Open a pull request against `main` describing what and why.

## Doc changes

This repo follows the AI ECP documentation standard (README, AGENTS.md,
the skill, quickstart, how-to, runbook, and the health files). Before a
commit that adds or moves a doc:

```bash
uv run pytest tests -q
uv run ruff check .
```

Require every `ecp-toolkit:` line to read PASS.

## Security

Do not open public issues for security vulnerabilities. See
[SECURITY.md](SECURITY.md) for the private reporting path.

## License

Apache-2.0. By contributing you agree your contributions are licensed
under the project's license.