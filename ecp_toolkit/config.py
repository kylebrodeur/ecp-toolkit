"""Shared config for the `ecp` control plane.

One file at ``~/.config/ai-ecp/config.json`` (mode 600), one section per kit
under ``kits``, plus the ``repos.root`` key the fleet-level commands use:

```json
{
  "kits": {
    "repo-guards": {"root": "/path/to/checkout"},
    "actions-runner": {"root": "/path/to/checkout"}
  },
  "repos": {"root": "/path/to/parent/dir"}
}
```

Override rules, from the design:

- ``$ECP_CONFIG`` changes the file path.
- Every field is also overridable by environment variable, because an
  operator override should never require editing a config file: a kit's
  ``root`` reads ``ECP_<KIT>_ROOT`` (the kit name upper cased, dashes as
  underscores), and ``repos.root`` reads ``ECP_REPOS_ROOT``.

Secrets are names only, everywhere, including in this file. A kit that needs
credentials declares the NAMES in its own manifest; a value is handed over on
stdin or through an explicit mode-0600 temp file, never in a process argv, a
config file, or the vendor tree.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

CONFIG_PATH_DEFAULT = Path.home() / ".config" / "ai-ecp" / "config.json"

CONFIG_ENV = "ECP_CONFIG"
REPOS_ROOT_ENV = "ECP_REPOS_ROOT"

# The committed lanes, in family order (catalog/INDEX.md). The order is what
# `ecp doctor` and `ecp status` iterate; a kit that is not checked out still
# appears there, as absent.
KITS = (
    "ecp-toolkit",
    "repo-guards",
    "actions-runner",
    "agent-workspace-kit",
    "docs-policy-kit",
    "op-safe",
    "omp-rpc-cli",
)


def config_path() -> Path:
    """The config file path: ``$ECP_CONFIG`` when set, else the default."""
    env = os.getenv(CONFIG_ENV, "").strip()
    if env:
        return Path(env).expanduser()
    return CONFIG_PATH_DEFAULT


def load() -> dict[str, Any]:
    """Read the config file, or ``{}`` when absent."""
    path = config_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(
            f"config {path} is not valid JSON: {exc}. Fix: repair or remove the file, then `ecp setup`"
        ) from None
    if not isinstance(data, dict):
        raise SystemExit(f"config {path} must hold a JSON object. Fix: rewrite it with `ecp setup`")
    return data


def write(data: dict[str, Any]) -> Path:
    """Persist the config and return the path. Mode 600."""
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)
    return path


def kit_section(kit: str) -> dict[str, Any]:
    """One kit's file settings, or ``{}`` when the kit has no section."""
    return dict(load().get("kits", {}).get(kit, {}))


def kit_root(kit: str) -> Path | None:
    """One kit's checkout root: env override first, then the config file.

    Returns None when the kit has neither. Absence is a normal state (repo
    presence is the signal), so this is a resolve, not a gate.
    """
    env_name = _kit_root_env(kit)
    env = os.getenv(env_name, "").strip()
    if env:
        return Path(env).expanduser()
    value = str(kit_section(kit).get("root", "")).strip()
    if value:
        return Path(value).expanduser()
    return None


def _kit_root_env(kit: str) -> str:
    """The env var that overrides one kit's root: ``ECP_<KIT>_ROOT``."""
    return f"ECP_{kit.upper().replace('-', '_')}_ROOT"


def repos_root() -> Path | None:
    """Where the kit repos live in fleet mode: env override, then config.

    Returns None when neither is set. The fleet-level commands report the
    absence (``ecp doctor`` says what is missing and how to fix it); the
    consumer-mode paths never read this key.
    """
    env = os.getenv(REPOS_ROOT_ENV, "").strip()
    if env:
        return Path(env).expanduser()
    value = str(load().get("repos", {}).get("root", "")).strip()
    if value:
        return Path(value).expanduser()
    return None


def repos_root_or_exit() -> Path:
    """``repos_root()`` with the exact-fix error when it is not configured."""
    root = repos_root()
    if root is None:
        raise SystemExit(
            "the repos root is not configured. Fix with EITHER:\n"
            "  ecp setup --repos-root <dir-holding-the-kit-repos>   (writes the config file)\n"
            "  export ECP_REPOS_ROOT=<dir-holding-the-kit-repos>"
        )
    if not root.is_dir():
        raise SystemExit(
            f"the configured repos root {root} is not a directory. "
            "Fix: correct the path with `ecp setup --repos-root <dir>` or unset ECP_REPOS_ROOT"
        )
    return root


def require(kit: str, keys: tuple[str, ...]) -> dict[str, Any]:
    """One kit's section, gated on the keys a command declared.

    The gate every manifest command with a ``requires`` list goes through:
    it names the missing keys and the two real fix lines (the kit's env
    overrides first, then ``ecp setup``), and exits 2. The design contract:
    the gate reports the exact fix.
    """
    section = kit_section(kit)
    missing = [key for key in keys if not section.get(key)]
    if not missing:
        return section
    env_names = [_kit_root_env(kit) if key == "root" else f"ECP_{kit.upper().replace('-', '_')}_{key.upper()}"
                 for key in missing]
    fixes = []
    for env_name in env_names:
        fixes.append(f"  export {env_name}=<value>")
    raise SystemExit(
        f"{kit} is not configured: missing {', '.join(missing)}. Fix with EITHER:\n"
        + "\n".join(fixes)
        + "\n"
        + f"  ecp setup   (writes the config file at {config_path()})"
    )
