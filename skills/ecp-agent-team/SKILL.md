---
name: ecp-agent-team
description: Use when setting up, running, or debugging a multi-agent team through the AI ECP control plane: the two operating modes, the manifest rules a team must satisfy, and the handoff rules that survive a session.
---

# Running an ECP agent team

The agent-team subsystem is two operating modes over one manifest.

## The two modes

**Mode A: agent-driven `omp`.** An agent uses the omp-rpc skills to drive
a persistent `omp` session over a Unix socket: send a prompt, switch
models, steer a running turn, read session stats. Use it for delegated
long-running work, where a persistent context that accumulates across
turns is the point.

**Mode B: multiplexed Zellij team.** Role-specific `omp` sessions launch
into a Zellij layout, one pane per role, each with its own session dir,
model, profile, and link name. `agent-workspace-kit` owns mode B; its
manifest rules below are what its preflight validates. Use it for
parallel lanes with distinct roles, where seeing the whole team at once
is the point.

The modes are complementary; each can use the other.

## The manifest is the single description

A team is described in ONE manifest, and that manifest can launch it.

A launcher that hardcodes each role's model, cwd, and prompt path is a
SECOND description of the same team, and the two disagree silently. This
is not hypothetical: a role file lived at one path while the launcher
derived its prompt path from a naming convention, so the role started
with a 19-byte stub prompt instead of its 1.5 KB profile, for months,
without an error. The manifest declared the correct path the whole time.

## Manifest rules

| Field | Rule |
|---|---|
| `cwd` | MUST already exist. A role cannot start in a directory that is not there. |
| `sessionDir` | Need not exist. Launchers create it before first use, so a missing one is normal on a clean checkout and warns rather than fails. |
| `worktree` | Optional per-lane checkout (`{path, branch}`). A role carries `cwd` OR a worktree, never both. |
| `profile` | Required, repo-relative. |
| `prompt`, `config` | Optional, repo-relative, must exist if declared. |
| `linkName` | Optional; defaults to `<roleKey>@<team.group>`. Two roles may not share one. |
| `skills.required` | Missing is an ERROR. |
| `skills.optional` | Missing is a WARNING. |
| `tools.*` | Declared intent only; never granted. |

Every path is repo-relative, so a manifest never carries an absolute path
that works on one machine only.

## Preflight before any pane

Validate the manifest BEFORE creating any pane. The launcher's read-only
mode is the gate; the kit's own commands are the way to run it (for
`agent-workspace-kit`, that is `teamctl check`):

```bash
teamctl check --root <team-repo>
```

This turns "a pane died on startup because a profile went missing" into a
clear failure before any pane exists. Read-only inspection modes never
write.

Zellij is a different layer, not an integration. A manifest that can
launch does not replace a pane layout; a repo that depends on a Zellij
layout keeps it and adds the preflight.

## Daemon safety (mode A)

- `busy` is the unit of safety. Concurrent sends are rejected (offer
  `steer` instead), and `stop` is gated on it. `--force` overrides.
- The approval guard is a deny-list at the single approval chokepoint, so
  the daemon runs in the approval-capable mode, not the headless one.
- The guard is a net, not a sandbox. It catches obvious catastrophes; a
  determined command can evade it. Real isolation is a container or a
  throwaway checkout.
- Cleanup touches only the daemon's own files. It never touches the
  session's working directory.

## Handoff rules

- **Artifacts, not chat.** A handoff doc naming files, commands, and
  acceptance criteria outlives the session. "We discussed it" does not.
  Chat-only coordination loses items within one session.
- **Verify the claim class, not the claim.** "Tests pass" means run the
  suite and read the count line. "Verified live" means run one live check.
  "Documented" means open the file. Three classes, three cheap
  verifications, none requiring trust.
- **Claims expire; state moves under you.** A handoff doc's "the edge is
  down" may be hours stale. Cheap live probes outrank any memo.
- **The verification hierarchy is cheapest-first:** file existence and
  content grep, then the oracle scripts by exit code, then the test suite
  count line, then live behavior.
- **Review the diff stat before every commit,** especially after a tool
  run that touched many files. A wrong-repo edit is recoverable in
  minutes when caught by diff review, and expensive when it is not.

## When a team is unresponsive

1. Check whether the lane is actually frozen: read the transcript's
   mtimes, not a status note.
2. If the lane is silent, wake it and wait for a real response before
   taking over.
3. If it does not respond, take over explicitly: state that the lane was
   unresponsive, preserve its WIP, and continue.
4. Never silently restart a lane whose state you have not read.
