---
name: ecp-catalog
description: Use when reading the AI ECP family catalog to place a kit or understand a repo's state: what the repo-state values mean, how a row implies its install path, and where a row correction belongs.
---

# Reading the ECP catalog

The family's catalog is ONE table of its repos: what exists today, where
it lives, what it becomes. A consumer runs it through the control plane:

```bash
ecp catalog
```

It is a POINTER index. It cites paths; it never restates a repo's
documentation. A tool's own repo is its canonical docs home.

## The repo-state values

Five values. Visibility is NOT one of them: the Target column carries
where a repo ends up. These carry the MIGRATION state.

| Value | Meaning |
|---|---|
| `NO-REPO` | No repo exists yet; extract fresh into a new repo. |
| `PRIVATE-SCRUB-THEN-PUBLISH` | Private today; scrub, then publish. |
| `PUBLIC-NEEDS-CLEANUP` | Public and healthy enough to keep; a hygiene pass is owed. |
| `PUBLIC-OK` | Healthy public repo; no cleanup owed. |
| `PRIVATE-OK` | Healthy private repo, retained as private. |

Keep history and remote: adopt as a second checkout. Expect a large
refactor or a rename/consolidation: copy into a new repo and cut over.

## What a row answers

- **Is this kit real today?** Today (path) is where the code lives; an
  install line names the real command. A design-only row says so.
- **Is it on a registry?** The family's distribution policy: ONE registry
  entry, everything else from GitHub at a tag. A bare registry install
  in a kit's docs works only for really-published kits.
- **Is anything owed?** The repo-state + cleanup column names the owed
  work, with a check date on every state claim.

## Correcting a row

One row per repo; a correction belongs to the family's catalog lane (the
private control-plane repo). The rules that hold there: every cited path
exists, a maturity value carries a check date, a private repo retained as
private is `PRIVATE-OK` (never `PUBLIC-OK`), and a pending release task
is a release task, not a repo-hygiene one.
