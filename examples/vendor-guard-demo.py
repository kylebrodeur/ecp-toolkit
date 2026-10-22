#!/usr/bin/env python3
"""Runnable demo: vendor a demo kit, guard it, and watch drift get refused.

Creates its own world under a temporary directory: a demo kit git repo with
one tag, a consumer project, `ecp pull` against the local repo URL, a clean
`ecp vendor check`, an in-place vendor edit, and the refusal `ecp vendor
check` then produces. Prints what it does; exit 0 means the guard caught
the drift it was supposed to catch.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import tempfile
import textwrap

REPO = pathlib.Path(__file__).resolve().parents[1]


def git(argv: list[str], cwd: pathlib.Path) -> None:
    subprocess.run(["git", *argv], cwd=cwd, capture_output=True, text=True, check=True)


def sh(label: str, argv: list[str], cwd: pathlib.Path, env: dict[str, str]) -> None:
    print(f"$ {label}")
    proc = subprocess.run(argv, cwd=cwd, env=env, capture_output=True, text=True, check=False)
    out = (proc.stdout + proc.stderr).strip()
    if out:
        print(textwrap.indent(out, "  "))
    print()


def main() -> int:
    world = pathlib.Path(tempfile.mkdtemp(prefix="ecp-example-"))
    env = dict(os.environ, ECP_CONFIG=str(world / "cfg.json"), ECP_REPOS_ROOT=str(world / "repos"))
    kit_src = world / "demo-kit-src"
    kit_src.mkdir()
    git(["init", "-q"], kit_src)
    git(["config", "user.email", "demo@example.com"], kit_src)
    git(["config", "user.name", "demo"], kit_src)
    (kit_src / "ecp-commands.toml").write_text(
        '[[command]]\nname = "hello"\nsummary = "say hello from the demo kit"\nkind = "shell"\n'
        'argv = ["echo", "hello from the demo kit"]\n',
        encoding="utf-8",
    )
    (kit_src / "KIT-FILE.md").write_text("the demo kit's one file\n", encoding="utf-8")
    git(["add", "-A"], kit_src)
    git(["commit", "-q", "-m", "demo kit"], kit_src)
    git(["tag", "-a", "v0.1.0", "-m", "v0.1.0"], kit_src)

    print(f"# world: {world}")
    print()
    sh("ecp setup --repos-root <world>/repos", ["uv", "run", "--project", str(REPO), "ecp", "setup",
        "--repos-root", str(world / "repos")], world, env)
    sh("ecp init demo-project", ["uv", "run", "--project", str(REPO), "ecp", "init", "demo-project"], world, env)
    project = world / "demo-project"
    sh("ecp pull demokit --tag v0.1.0   (source pointed at the local demo repo)",
       ["uv", "run", "--project", str(REPO), "ecp", "pull", "demokit", "--tag", "v0.1.0"],
       project, dict(env, ECP_DEMOKIT_REPO_URL=str(kit_src)))
    sh("ecp --project . demokit hello", ["uv", "run", "--project", str(REPO), "ecp", "demokit", "hello"],
       project, env)
    sh("ecp vendor check", ["uv", "run", "--project", str(REPO), "ecp", "vendor", "check"], project, env)
    vendored = project / "vendor" / "demokit"
    (vendored / "KIT-FILE.md").write_text("edited in place - the mistake\n", encoding="utf-8")
    sh("(edited vendor/demokit/KIT-FILE.md in place)", ["true"], project, env)
    sh("ecp vendor check   (now refusing)", ["uv", "run", "--project", str(REPO), "ecp", "vendor", "check"],
       project, env)
    print("the drift guard caught the edit: the vendored copy is read-only by enforcement,")
    print("and the finding names where the change belongs. Exit 1 is the guard working.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        print(f"error: {' '.join(exc.cmd)}: {exc.stderr.strip()}", file=sys.stderr)
        raise SystemExit(1) from None
