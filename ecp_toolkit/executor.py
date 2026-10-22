"""The executor: run a declared command by its kind.

A closed vocabulary of run kinds, from the design:

- ``shell``  run a kit's own script or command in the kit's checkout.
- ``python`` invoke a kit's Python entry point in the kit's checkout.
- ``probe``  a health/presence check for the kit.

Whole-surface ``[passthrough]`` delegations and per-command
``passthrough = true`` flags forward the caller's extra arguments to the
kit's own CLI verbatim, so the kit's own parser keeps owning parsing.

Execution roots never mix (the two modes):

- Inside a consumer project, kit code is read from and run in
  ``<project>/vendor/<kit>/``. A consumer project NEVER falls back to a
  shared checkout: that would break the vendor boundary, because the pinned
  tag would no longer be what actually runs.
- In fleet mode, kit code is read from and run in the checkout under the
  configured ``repos.root``.

The config gate runs before any command: a command's ``requires`` keys are
checked against the kit's config section, and a missing key is an error
naming the exact fix, not a mid-run surprise.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from . import config, manifest

# Default subprocess budget for a shell/python command that declares none.
DEFAULT_TIMEOUT = 900


def _gate(kit: str, requires: tuple[str, ...]) -> None:
    """Enforce a command's declared config keys with the exact-fix error."""
    if requires:
        config.require(kit, requires)


def _checkout_root(kit: str, project_root: Path | None) -> Path:
    """Where a kit's code is read from and run in, by mode; never mixing.

    Project mode wins when ``project_root`` is given, and the kit MUST be
    vendored there: the fallback to a shared checkout is the bug the vendor
    boundary exists to prevent.
    """
    if project_root is not None:
        vendored = project_root / "vendor" / kit
        if not vendored.is_dir():
            raise SystemExit(
                f"{kit} is not vendored in this project ({vendored}); "
                f"fix: run `ecp pull {kit} --tag <release>` first"
            )
        return vendored
    return config.repos_root_or_exit() / kit


def _fmt(exc: BaseException) -> str:
    """A short error line for a failed subprocess launch."""
    return str(exc).strip() or type(exc).__name__


def run(
    kit: str,
    spec: manifest.CommandSpec,
    extra: list[str] | None = None,
    *,
    project_root: Path | None = None,
) -> int:
    """Execute one declared command by its kind; return the process exit code."""
    _gate(kit, spec.requires)
    extra = list(extra or [])
    if spec.passthrough:
        return _run_passthrough_argv(kit, spec, extra, project_root=project_root)

    checkout = _checkout_root(kit, project_root)
    if spec.kind == "shell":
        argv = [*spec.argv, *extra]
        try:
            proc = subprocess.run(argv, cwd=checkout, check=False, timeout=spec.timeout or DEFAULT_TIMEOUT)
        except FileNotFoundError as exc:
            print(f"{kit}: {spec.argv[0]} is not available on PATH: {_fmt(exc)}", file=sys.stderr)
            return 127
        except subprocess.TimeoutExpired:
            print(f"{kit}: {spec.argv[0]} timed out after {spec.timeout or DEFAULT_TIMEOUT}s", file=sys.stderr)
            return 1
        return proc.returncode

    if spec.kind == "python":
        argv = ["uv", "run", "python", *spec.argv, *extra]
        try:
            proc = subprocess.run(argv, cwd=checkout, check=False, timeout=spec.timeout or DEFAULT_TIMEOUT)
        except FileNotFoundError:
            print(
                "uv is not available on PATH. Fix: install uv (https://docs.astral.sh/uv/getting-started/installation/)",
                file=sys.stderr,
            )
            return 127
        except subprocess.TimeoutExpired:
            print(f"{kit}: the python entry point timed out after {spec.timeout or DEFAULT_TIMEOUT}s", file=sys.stderr)
            return 1
        return proc.returncode

    if spec.kind == "probe":
        return _probe(kit, spec, checkout, extra)

    # Unreachable: the loader validates the kind vocabulary.
    raise SystemExit(f"unknown command kind {spec.kind!r}")


def run_passthrough(
    kit: str,
    spec: manifest.PassthroughSpec,
    extra: list[str] | None = None,
    *,
    project_root: Path | None = None,
) -> int:
    """Delegate the kit's whole surface to its own console script.

    ``ecp <kit> <anything...>`` -> the passthrough argv plus the caller's
    extra arguments, run in the kit's checkout, argv preserved verbatim: the
    kit's own argparse owns parsing, and ``ecp`` never re-implements a
    kit's surface.
    """
    _gate(kit, spec.requires)
    return _run_passthrough_argv(kit, spec, list(extra or []), project_root=project_root)


def _run_passthrough_argv(
    kit: str,
    spec: manifest.CommandSpec | manifest.PassthroughSpec,
    extra: list[str],
    *,
    project_root: Path | None,
) -> int:
    checkout = _checkout_root(kit, project_root)
    argv = [*spec.argv, *extra]
    try:
        proc = subprocess.run(argv, cwd=checkout, check=False, timeout=DEFAULT_TIMEOUT)
    except FileNotFoundError as exc:
        print(f"{kit}: {spec.argv[0]} is not available on PATH: {_fmt(exc)}", file=sys.stderr)
        return 127
    except subprocess.TimeoutExpired:
        print(f"{kit}: the command timed out after {DEFAULT_TIMEOUT}s", file=sys.stderr)
        return 1
    return proc.returncode


def _probe(kit: str, spec: manifest.CommandSpec, checkout: Path, extra: list[str]) -> int:
    """The kit's health/presence check: the manifest's probe argv, if any.

    A kit manifest declares a probe as a real argv (its own ``--version`` or
    a presence script). Nothing declared: the checkout itself is the thing
    being probed, so presence is the result.
    """
    if not spec.argv:
        state = "present" if checkout.is_dir() else "missing"
        print(f"{kit} probe status={state} ({checkout})")
        return 0 if state == "present" else 1
    argv = [*spec.argv, *extra]
    try:
        proc = subprocess.run(argv, cwd=checkout, check=False, capture_output=True, text=True,
                              timeout=spec.timeout or 120)
    except FileNotFoundError as exc:
        print(f"{kit} probe status=error ({spec.argv[0]} is not on PATH: {_fmt(exc)})")
        return 1
    except subprocess.TimeoutExpired:
        print(f"{kit} probe status=timeout")
        return 1
    state = "ok" if proc.returncode == 0 else f"failed (exit {proc.returncode})"
    print(f"{kit} probe status={state}")
    if proc.returncode != 0 and (proc.stdout or proc.stderr):
        sys.stderr.write((proc.stdout + proc.stderr).strip() + "\n")
    return proc.returncode
