"""Per-kit command manifests: the loader and the specs.

Each kit repo ships an ``ecp-commands.toml`` declaring the commands
``ecp <kit>`` offers. ``ecp`` reads the manifest at parser-build time and
mounts one subcommand per declared command. Adding a command becomes a
repo-side edit (one TOML table), so ``ecp`` never grows a per-kit wrapper.

Manifest shape
--------------
A manifest declares EITHER named ``[[command]]`` tables OR a whole-surface
``[passthrough]`` table - not both, and never neither. An optional
``[defaults]`` table merges into every ``[[command]]`` (a command's own
value wins).

Run kinds (the executor's closed vocabulary):
  shell   run a kit's own script or command in the kit's checkout
  python  invoke a kit's Python entry point in the kit's checkout
  probe   a health/presence check for the kit

``passthrough`` is not a run kind. It is the separate, mutually exclusive
manifest shape (a kit that owns its own CLI, e.g. ``guv``, ``arun``,
``omp-rpc``). A whole-surface ``[passthrough]`` table delegates
``ecp <kit> <anything...>`` argv verbatim, so the kit's own parser owns
parsing. An individual ``[[command]]`` may ALSO carry ``passthrough = true``,
which forwards that command's extra arguments to the kit's CLI; that is a
per-command flag, validated as a boolean, and distinct from the shape.

Validation is fail closed at load time: a malformed manifest is an error
naming the manifest and the problem, with a fix line, never a silently
skipped command.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

MANIFEST_NAME = "ecp-commands.toml"

# The run kinds the host implements. A manifest naming anything else is a
# repo-side error and fails closed at load time. Whole-surface delegation to
# a repo's own CLI is a separate manifest shape ([passthrough]), not a kind.
KINDS = ("shell", "python", "probe")

# The kinds whose command table requires a non-empty argv.
ARGV_KINDS = ("shell", "python")


class CommandManifestError(Exception):
    """A manifest failed validation. ``args`` = (manifest_file, message)."""


@dataclass(frozen=True)
class CommandSpec:
    """One declared ``[[command]]``."""

    name: str
    summary: str
    kind: str
    argv: tuple[str, ...] = ()
    requires: tuple[str, ...] = ()
    timeout: int | None = None
    passthrough: bool = False


@dataclass(frozen=True)
class PassthroughSpec:
    """A whole-surface ``[passthrough]`` delegation to the kit's own CLI."""

    argv: tuple[str, ...]
    summary: str
    requires: tuple[str, ...] = ()


@dataclass(frozen=True)
class Manifest:
    """One kit's parsed manifest: its commands, or its passthrough surface."""

    commands: list[CommandSpec] = field(default_factory=list)
    passthrough: PassthroughSpec | None = None


def manifest_path(repo: Path) -> Path:
    """The manifest location inside a kit checkout (the repo root)."""
    return repo / MANIFEST_NAME


def _as_str_list(path: Path, value: Any, what: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise CommandManifestError(str(path), f"{what} must be a list of strings")
    return tuple(value)


def load(repo: Path) -> Manifest | None:
    """Parse ``<repo>/ecp-commands.toml``; None when the kit ships none.

    Raises CommandManifestError on malformed TOML, an unknown kind, a command
    missing name/summary/kind, a kind whose required fields (argv) are
    absent, a non-boolean per-command passthrough, a non-integer timeout, a
    non-string-list requires, or neither-or-both of commands/passthrough.
    """
    path = manifest_path(repo)
    if not path.is_file():
        return None
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise CommandManifestError(str(path), f"invalid TOML: {exc}") from None

    defaults = data.get("defaults", {})
    if not isinstance(defaults, dict):
        raise CommandManifestError(str(path), "[defaults] must be a table")

    has_commands = "command" in data
    has_passthrough = "passthrough" in data
    if has_commands and has_passthrough:
        raise CommandManifestError(str(path), "declare EITHER [[command]] entries OR [passthrough], not both")
    if not has_commands and not has_passthrough:
        raise CommandManifestError(str(path), "missing [[command]] entries or a [passthrough] table")

    if has_passthrough:
        body = data["passthrough"]
        if not isinstance(body, dict):
            raise CommandManifestError(str(path), "[passthrough] must be a table")
        argv = _as_str_list(path, body.get("argv"), "[passthrough].argv")
        if not argv:
            raise CommandManifestError(str(path), "[passthrough] requires a non-empty argv")
        summary = body.get("summary")
        if not isinstance(summary, str) or not summary:
            raise CommandManifestError(str(path), "[passthrough] requires a non-empty summary")
        return Manifest(
            passthrough=PassthroughSpec(
                argv=argv,
                summary=summary,
                requires=_as_str_list(path, body.get("requires"), "[passthrough].requires"),
            )
        )

    raw_commands = data["command"]
    if not isinstance(raw_commands, list) or not raw_commands:
        raise CommandManifestError(str(path), "[[command]] entries must be a non-empty list")
    commands: list[CommandSpec] = []
    for body in raw_commands:
        if not isinstance(body, dict):
            raise CommandManifestError(str(path), "each [[command]] must be a table")
        merged: dict[str, Any] = {**defaults, **body}
        name = merged.get("name")
        summary = merged.get("summary")
        kind = merged.get("kind")
        if not isinstance(name, str) or not name:
            raise CommandManifestError(str(path), "a [[command]] is missing a non-empty name")
        if not isinstance(summary, str) or not summary:
            raise CommandManifestError(str(path), f"command {name!r} is missing a non-empty summary")
        if not isinstance(kind, str) or not kind:
            raise CommandManifestError(str(path), f"command {name!r} is missing a non-empty kind")
        if kind not in KINDS:
            raise CommandManifestError(
                str(path), f"command {name!r} has unknown kind {kind!r}; supported: {list(KINDS)}"
            )
        argv = _as_str_list(path, merged.get("argv"), f"command {name!r} argv")
        if kind in ARGV_KINDS and not argv:
            raise CommandManifestError(str(path), f"command {name!r} (kind {kind!r}) requires a non-empty argv")
        timeout = merged.get("timeout")
        if timeout is not None and not isinstance(timeout, int):
            raise CommandManifestError(str(path), f"command {name!r} timeout must be an integer")
        passthrough_flag = merged.get("passthrough", False)
        if not isinstance(passthrough_flag, bool):
            raise CommandManifestError(str(path), f"command {name!r} passthrough must be a boolean")
        commands.append(
            CommandSpec(
                name=name,
                summary=summary,
                kind=kind,
                argv=argv,
                requires=_as_str_list(path, merged.get("requires"), f"command {name!r} requires"),
                timeout=timeout,
                passthrough=passthrough_flag,
            )
        )
    return Manifest(commands=commands)


def discover(root: Path) -> dict[str, Path]:
    """The kits that ship a manifest under ``root``: ``{kit: checkout}``.

    Discovery follows the execution mode, and the two never mix: inside a
    consumer project the roots are ``vendor/<kit>/`` checkouts; in fleet
    mode they are the checkouts under the configured repos root. A fresh
    ecp-only clone mounts nothing, which is the signal working, not failing.
    """
    return {
        name: child
        for name, child in checkouts(root).items()
        if manifest_path(child).is_file()
    }


def checkouts(root: Path) -> dict[str, Path]:
    """Every kit checkout under ``root``, manifest or not: ``{name: dir}``.

    Presence listing, for ``ecp doctor``: a checkout that ships no manifest
    is PRESENT and mounts nothing, which doctor must say in so many words.
    """
    if not root.is_dir():
        return {}
    kits: dict[str, Path] = {}
    for child in sorted(root.iterdir()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        kits[child.name] = child
    return kits
