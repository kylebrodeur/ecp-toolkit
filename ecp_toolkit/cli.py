"""ecp: the one operator CLI for the AI Engineering Control Plane.

Fleet-level commands (no single kit's) plus one command group per kit repo
that ships an ``ecp-commands.toml`` manifest. The control plane mounts; it
never hard-codes a wrapper per kit.

Exit codes: 0 ok; 1 failure; 2 an unmet configuration requirement (the
config gate's exit, the exact-fix error). ``argparse`` itself exits 2 on a
usage error, which is the same shape.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from . import config, executor, manifest, project


def _fleet_roots() -> tuple[Path | None, dict[str, Path]]:
    """Fleet-mode discovery over the configured repos root.

    Returns ``(root, kits)``: the root (None when unconfigured) and the
    kit checkouts that ship a manifest. Repo presence is the signal.
    """
    root = config.repos_root()
    if root is None:
        return None, {}
    return root, manifest.discover(root)


# ── Fleet commands ──────────────────────────────────────────────────────────


def cmd_setup(args: argparse.Namespace) -> int:
    """Write the config file: one section per kit, mode 600.

    Never prints or stores a secret value: sections hold roots and NAMES
    only.
    """
    data: dict[str, Any] = {}
    existing = config.load()
    kits = dict(existing.get("kits", {}))
    if args.repos_root:
        data["repos"] = {"root": str(Path(args.repos_root).expanduser())}
    elif existing.get("repos"):
        data["repos"] = existing["repos"]
    if args.kit and args.root:
        kits[args.kit] = {"root": str(Path(args.root).expanduser())}
    data["kits"] = kits
    path = config.write(data)
    print(f"wrote {path} (mode 600)")
    if not data.get("repos", {}).get("root"):
        print(
            "note: repos.root is not set; the fleet-level commands need it. "
            "Fix: `ecp setup --repos-root <dir-holding-the-kit-repos>`"
        )
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    """List which kits are present and what each one declares.

    A kit that is not checked out is reported as absent: repo presence is
    the signal, and the absence is a finding an operator acts on, not a
    silent skip. A malformed manifest is a loud error with a fix line.
    """
    root, kits = _fleet_roots()
    if args.json:
        return _doctor_json(root, kits)
    if root is None:
        print(
            "no repos root configured. Fix with EITHER:\n"
            "  ecp setup --repos-root <dir-holding-the-kit-repos>\n"
            "  export ECP_REPOS_ROOT=<dir-holding-the-kit-repos>"
        )
        return 1
    if not root.is_dir():
        print(f"the configured repos root {root} is not a directory. Fix: correct the path or unset ECP_REPOS_ROOT")
        return 1
    print(f"repos root: {root}")
    known = set(config.KITS)
    present = manifest.checkouts(root)
    for kit in config.KITS:  # the committed lanes, in family order
        checkout = present.get(kit)
        if checkout is None:
            print(f"  {kit}: absent (not checked out under {root})")
            continue
        try:
            loaded = manifest.load(checkout)
        except manifest.CommandManifestError as exc:
            manifest_file, message = exc.args
            raise SystemExit(
                f"invalid command manifest {manifest_file}: {message}\nfix the file in that repo"
            ) from None
        if loaded is None:
            print(f"  {kit}: present, ships no manifest (mounts nothing; a kit may ship no manifest)")
            continue
        if loaded.passthrough is not None:
            spec = loaded.passthrough
            print(f"  {kit}: passthrough -> {list(spec.argv)} ({spec.summary})")
            continue
        commands = ", ".join(spec.name for spec in loaded.commands) or "(no commands)"
        print(f"  {kit}: {commands}")
    unknown = [name for name in present if name not in known]
    if unknown:
        print(f"  (also checked out, not committed lanes: {', '.join(unknown)})")
    vendored = _project_overrides_if_any(args)
    for line in vendored:
        print(line)
    return 0


def _project_overrides_if_any(args: argparse.Namespace) -> list[str]:
    """The recorded allow-local-changes overrides visible in doctor output."""
    project_root = getattr(args, "project", None)
    if not project_root:
        candidate = Path.cwd() / project.RECORD_DIR / project.RECORD_FILE
        if not candidate.is_file():
            return []
        project_root = Path.cwd()
    record = project.read_record(Path(project_root))
    overrides = record.get("state", {}).get("overrides", [])
    if not overrides:
        return []
    return [f"  override recorded: {o['override']} on {o['kit']}" for o in overrides]


def _doctor_json(root: Path | None, kits: dict[str, Path]) -> int:
    """The doctor's JSON shape: per-kit presence and declarations."""
    out: dict[str, Any] = {"repos_root": str(root) if root else None, "kits": {}}
    for kit in config.KITS:
        checkout = kits.get(kit)
        entry: dict[str, Any] = {"checkout": str(checkout) if checkout else None, "manifest": None}
        if checkout:
            try:
                loaded = manifest.load(checkout)
            except manifest.CommandManifestError:
                raise
            if loaded and loaded.passthrough:
                entry["manifest"] = {"shape": "passthrough", "argv": list(loaded.passthrough.argv)}
            elif loaded:
                entry["manifest"] = {
                    "shape": "commands",
                    "commands": [
                        {"name": spec.name, "kind": spec.kind, "summary": spec.summary} for spec in loaded.commands
                    ],
                }
        out["kits"][kit] = entry
    print(json.dumps(out, indent=2))
    return 0


def cmd_catalog(args: argparse.Namespace) -> int:
    """Print the kit catalog: what each kit is and where it lives."""
    del args  # read-only; no flags today
    rows = [
        ("ecp-toolkit", "control plane", "this CLI: the fleet verbs and the manifest mount"),
        ("repo-guards", "governance", "guv: repo-discipline gates as exit codes"),
        ("actions-runner", "agent pipeline", "arun: config-driven local agent/model pipeline"),
        ("agent-workspace-kit", "agent team", "manifest-driven role launcher for multi-agent teams"),
        ("docs-policy-kit", "docs/publication", "config-driven docs policy engine"),
        ("op-safe", "secrets", "op://-reference resolution, values land in mode-0600 files only"),
        ("omp-rpc-cli", "agent runtime", "omp: persistent RPC sessions over the local agent runtime"),
    ]
    print(f"{'kit':<22} {'lane':<16} what it is")
    for kit, lane, what in rows:
        print(f"{kit:<22} {lane:<16} {what}")
    print()
    print("The authoritative table: catalog/INDEX.md in the system repo.")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    """Per-kit row: version, CI state, hook state. Read-only over the fleet.

    Seeded from the Modal family's proven status script: one row per repo.
    Missing binaries degrade to a ``-`` column, never a crash.
    """
    root, kits = _fleet_roots()
    if root is None:
        print(
            "no repos root configured. Fix with EITHER:\n"
            "  ecp setup --repos-root <dir-holding-the-kit-repos>\n"
            "  export ECP_REPOS_ROOT=<dir-holding-the-kit-repos>"
        )
        return 1
    print(f"{'kit':<22} {'version':<10} {'ci':<12} hooks")
    for kit in config.KITS:
        checkout = kits.get(kit)
        if checkout is None:
            print(f"{kit:<22} {'-':<10} {'-':<12} absent")
            continue
        version = _kit_version(checkout)
        ci, hooks = _kit_ci_state(checkout, args.no_net)
        print(f"{kit:<22} {version:<10} {ci:<12} {hooks}")
    return 0


def _kit_version(checkout: Path) -> str:
    """The checkout's pyproject version, or '-'."""
    pyproject = checkout / "pyproject.toml"
    if not pyproject.is_file():
        return "-"
    text = pyproject.read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.startswith("version = "):
            return line.split("=", 1)[1].strip().strip('"')
    return "-"


def _kit_ci_state(checkout: Path, no_net: bool) -> tuple[str, str]:
    """One kit's CI state and hook state as short strings."""
    hooks = f"hooksPath={_git_out(checkout, 'config', 'core.hooksPath') or '-'}"
    del no_net  # CI state is local-only in this skeleton; a probe flag arrives with the release wiring
    return "local", hooks


def _git_out(checkout: Path, *argv: str) -> str:
    """One git query's trimmed stdout, or ''."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(checkout), *argv], capture_output=True, text=True, check=False, timeout=30
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""
    return proc.stdout.strip()


def cmd_init(args: argparse.Namespace) -> int:
    """Scaffold a consumer project: the vendor dir and the overlay dir."""
    base = Path(args.project_dir).expanduser().resolve() if args.project_dir else Path.cwd()
    try:
        root = project.init_project(base, args.project_id)
    except project.ProjectError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"initialized project {root}")
    print("next:")
    print("  ecp pull <kit> --tag <release>     # vendor a kit, pinned to a tag")
    print("  ecp vendor check                   # refuse a drifted vendor tree")
    return 0


def cmd_pull(args: argparse.Namespace) -> int:
    """Vendor a tag-pinned copy of a kit into the current project."""
    project_root = _resolve_project_root(args)
    if project_root is None:
        print(_not_project_error(), file=sys.stderr)
        return 1
    try:
        project.pull(
            project_root,
            args.kit,
            tag=args.tag,
            allow_local_changes=args.allow_local_changes,
        )
    except project.ProjectError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


def _resolve_project_root(args: argparse.Namespace) -> Path | None:
    """The project root for a per-kit command, honoring the mode flags.

    ``--fleet`` forces None (fleet mode even from inside a project);
    ``--project PATH`` wins; otherwise the current directory being a
    project (record present) is project mode.
    """
    explicit = getattr(args, "project", None)
    if getattr(args, "fleet", False):
        if explicit:
            return Path(explicit).expanduser()
        return None
    if explicit:
        return Path(explicit).expanduser()
    candidate = Path.cwd() / project.RECORD_DIR / project.RECORD_FILE
    if candidate.is_file():
        return Path.cwd()
    return None


def _not_project_error() -> str:
    return (
        "this is not a consumer project (no .ecp/config.json here). "
        "Fix: run `ecp init [<project-id>]` first, or pass --project <path>"
    )


def cmd_vendor_check(args: argparse.Namespace) -> int:
    """The drift guard: refuse a drifted vendor tree."""
    project_root = _resolve_project_root(args)
    if project_root is None:
        print(_not_project_error(), file=sys.stderr)
        return 1
    if args.kit:
        try:
            ok, findings = project.vendor_check(project_root, args.kit)
        except (project.ProjectError, json.JSONDecodeError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
    else:
        try:
            ok, findings = project.vendor_check_all(project_root)
        except json.JSONDecodeError as exc:
            print(f"error: a provenance file is not valid JSON: {exc}", file=sys.stderr)
            return 1
    for finding in findings:
        print(finding, file=sys.stderr)
    print("vendor check: ok" if ok else "vendor check: DRIFTED (findings above)")
    return 0 if ok else 1


# ── Per-kit commands (declared by each repo's ecp-commands.toml) ────────────


def _kit_cmd(args: argparse.Namespace) -> int:
    """Run one manifest-declared command (dispatched by kind)."""
    project_root = _resolve_project_root(args)
    return executor.run(args._kit, args._spec, _extra_args(args), project_root=project_root)


def _kit_passthrough(args: argparse.Namespace) -> int:
    """Run a kit's whole-surface delegation to its own CLI."""
    project_root = _resolve_project_root(args)
    return executor.run_passthrough(args._kit, args._spec, _extra_args(args), project_root=project_root)


def _extra_args(args: argparse.Namespace) -> list[str]:
    """The forwarded tail: the REMAINDER dest, plus any parse_known extras."""
    remainder = list(getattr(args, "args", None) or [])
    forward = list(getattr(args, "_args", None) or [])
    return remainder + forward


def _mount_kit_commands(sub: argparse._SubParsersAction, project_root: Path | None) -> None:
    """Mount one ``ecp <kit>`` group where the mode says kit code lives.

    The two modes never mix (the execution-roots rule):

    - Project mode (``project_root`` given): each group mounts from that
      project's ``vendor/<kit>/`` manifest, so a project offers exactly what
      its pinned manifests declare. A kit that is not vendored mounts
      nothing, and the fleet checkout is NOT consulted: a consumer project
      never falls back to a shared checkout, so an unvendored kit's
      ``ecp <kit> ...`` fails with the executor's exact fix.
    - Fleet mode: each group mounts from the kit checkout under the
      configured repos root. A fresh ecp-only clone mounts nothing.

    A malformed manifest is a loud, actionable error rather than a silently
    missing command group.
    """
    if project_root is not None:
        kits = manifest.discover(Path(project_root) / project.VENDOR_DIR)
    else:
        root, kits = _fleet_roots()
        if root is None:
            return
    for kit, checkout in kits.items():
        try:
            loaded = manifest.load(checkout)
        except manifest.CommandManifestError as exc:
            manifest_file, message = exc.args
            raise SystemExit(f"invalid command manifest {manifest_file}: {message}") from None
        if loaded is None:
            continue

        group = sub.add_parser(kit, help=f"{kit} kit commands (from its ecp-commands.toml)")
        if loaded.passthrough is not None:
            spec = loaded.passthrough
            group.set_defaults(func=_kit_passthrough, _kit=kit, _spec=spec)
            group.add_argument("args", nargs=argparse.REMAINDER, help=argparse.SUPPRESS)
            continue

        cmd_sub = group.add_subparsers(dest="subcommand", required=True)
        for spec in loaded.commands:
            child = cmd_sub.add_parser(spec.name, help=spec.summary)
            if spec.passthrough:
                child.add_argument("args", nargs=argparse.REMAINDER, help=argparse.SUPPRESS)
            child.set_defaults(func=_kit_cmd, _kit=kit, _spec=spec)


# ── Parser ─────────────────────────────────────────────────────────────────


def build_parser(project_root: Path | None = None) -> argparse.ArgumentParser:
    """The parser: fleet commands, then the mounted kit groups.

    ``project_root`` is the mode separator: a project mounts its vendored
    manifests; None mounts the fleet checkout set.
    """
    p = argparse.ArgumentParser(
        prog="ecp",
        description="The AI ECP control plane: fleet commands plus one group per kit that ships a manifest",
    )
    p.add_argument(
        "--project",
        metavar="PATH",
        help="operate inside the consumer project at PATH (reads vendor/<kit>/, never a shared checkout)",
    )
    p.add_argument(
        "--fleet",
        action="store_true",
        help="force fleet mode even from inside a project directory (the mode separator)",
    )
    sub = p.add_subparsers(dest="command", required=True)

    setup_p = sub.add_parser("setup", help="write the config file (one section per kit, mode 600)")
    setup_p.add_argument("--repos-root", help="parent dir holding the kit repos")
    setup_p.add_argument("--kit", help="one kit's name, to seed its section with root")
    setup_p.add_argument("--root", help="that kit's checkout root")
    setup_p.set_defaults(func=cmd_setup)

    doctor_p = sub.add_parser("doctor", help="which kits are present and what each declares")
    doctor_p.add_argument("--json", action="store_true", help="emit JSON")
    doctor_p.set_defaults(func=cmd_doctor)

    cat_p = sub.add_parser("catalog", help="print the kit catalog")
    cat_p.set_defaults(func=cmd_catalog)

    status_p = sub.add_parser("status", help="per-kit version, CI state, and hook state (read-only)")
    status_p.add_argument("--no-net", action="store_true", help="no network probes; local state only")
    status_p.set_defaults(func=cmd_status)

    init_p = sub.add_parser("init", help="scaffold a consumer project (record, vendor/, overlays/)")
    init_p.add_argument("project_id", nargs="?", help="project id; omit to use the current directory")
    init_p.add_argument("--dir", dest="project_dir", help="the parent dir to init into (default: the current one)")
    init_p.set_defaults(func=cmd_init)

    pull_p = sub.add_parser("pull", help="vendor a tag-pinned copy of ONE kit into this project")
    pull_p.add_argument("kit", help="kit name, e.g. repo-guards")
    pull_p.add_argument("--tag", required=True, help="release tag to vendor at, e.g. v0.1.0")
    pull_p.add_argument(
        "--allow-local-changes",
        dest="allow_local_changes",
        action="store_true",
        help="proceed despite vendor drift; the override is recorded in the project state",
    )
    pull_p.set_defaults(func=cmd_pull)

    vendor_p = sub.add_parser("vendor", help="the vendored-copy guards")
    vendor_sub = vendor_p.add_subparsers(dest="vendor_command", required=True)
    vendor_check_p = vendor_sub.add_parser("check", help="refuse a drifted vendor tree")
    vendor_check_p.add_argument("kit", nargs="?", help="one kit (default: every recorded kit)")
    vendor_check_p.set_defaults(func=cmd_vendor_check)

    _mount_kit_commands(sub, project_root)
    return p


def main(project_root: Path | None = None) -> int:
    """The console entry point. ``project_root`` forces project mode."""
    forced_fleet = "--fleet" in sys.argv[1:]
    if project_root is None and not forced_fleet:
        # The mode is resolved BEFORE the parser builds: project mode mounts
        # the vendored manifests, fleet mode mounts the repos-root checkouts,
        # and the two never mix.
        cwd_record = Path.cwd() / project.RECORD_DIR / project.RECORD_FILE
        if cwd_record.is_file():
            project_root = Path.cwd()

    parser = build_parser(project_root)
    args, extras = parser.parse_known_args()
    explicit_project = getattr(args, "project", None)
    if getattr(args, "fleet", False) and explicit_project is None:
        # --fleet suppresses the project resolution: fleet mode, even from
        # inside a project directory.
        args.project = None
    elif explicit_project is None and project_root is not None:
        args.project = str(project_root)
    if extras:
        # A whole-surface passthrough forwards its tail verbatim (flags
        # included); a per-command passthrough forwards the command's extra
        # args. Anything else has no escape hatch: unknown args are an error.
        spec = getattr(args, "_spec", None)
        accepts = isinstance(spec, manifest.PassthroughSpec) or (
            isinstance(spec, manifest.CommandSpec) and spec.passthrough
        )
        if not accepts:
            parser.error(f"unrecognized arguments: {' '.join(extras)}")
        tail = extras[1:] if extras and extras[0] == "--" else extras
        args._args = (getattr(args, "_args", None) or []) + tail
    else:
        args._args = getattr(args, "_args", None) or []

    try:
        return int(args.func(args))
    except project.ProjectError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except SystemExit as exc:
        code = exc.code
        if isinstance(code, int):
            return code
        if code in (None, True):
            return 0
        if code is False:
            return 1
        # A str code (the config gate's exact-fix message et al.) prints and exits 2.
        print(code, file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
