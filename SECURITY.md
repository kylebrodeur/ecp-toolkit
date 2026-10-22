# Security Policy

## Supported Versions

| Version | Supported |
|---|---|
| latest tag | yes |
| older tags | best effort (backport security fixes as needed) |

## Reporting a Vulnerability

**Do not open a public issue for a security vulnerability.**

Use GitHub's **Private Vulnerability Reporting** to reach the
maintainer:

1. Go to the **Security** tab in this repository.
2. Click **"Report a vulnerability."**
3. Describe the issue, a reproduction path, and the affected version or
   tag.

You receive an acknowledgment within 72 hours. If you do not hear back,
follow up via the contact info on the maintainer's profile.

## Scope notes for the `ecp` control plane

The CLI is a control surface: it reads manifest files, resolves config,
and runs kit commands as subprocesses. Its trust boundaries, and the
reports that are most welcome:

- **Manifest execution:** an `ecp-commands.toml` declares subprocess
  argv values that `ecp` runs in the kit's checkout. Anything that lets
  an untrusted source place a manifest or a command value in that path
  is in scope: a manifest is code, and the repo owning it must be one
  the operator trusts.
- **Config resolution:** `ECP_CONFIG` and `~/.config/ai-ecp/`
  determine which config file loads, and the `ECP_<KIT>_*` env vars
  override per-kit fields. A path where attacker-supplied config or env
  reaches a subprocess is in scope.
- **The vendor operation:** `ecp pull` clones a repo URL derived from
  the kit name and checks out a tag, and `ecp vendor check` shells out
  to `git` inside vendored trees. Argument construction for those calls
  is in scope: every value must be exactly the configured or
  user-supplied value, never interpolated from a surprising source.
- **The passthrough forwarding:** `ecp <kit> <anything...>` forwards
  argv verbatim to the kit's own CLI. A bug that mangles the boundary
  between `ecp`'s own flags and the forwarded tail is in scope.

Secret values are out of scope for this CLI BY DESIGN: `ecp` never
handles a secret value (names only, everywhere). A report about a secret
VALUE flowing through `ecp` would name a real bug in a kit manifest or a
consumer config, and it is welcome.

## Disclosure Process

- Reports are triaged, confirmed, and fixed.
- Coordinated disclosure applies (60 to 120 days typical embargo).
- The reporter is credited in the security advisory and release notes
  unless anonymity is preferred.