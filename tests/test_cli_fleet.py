"""Tests for the CLI surface: the fleet commands, the mount, and dispatch.

What is pinned here: the manifest loader's fail-closed behavior at mount
time (a malformed manifest is a loud error, never a silently skipped
command), repo-presence discovery (a fresh clone mounts nothing), the
config gate's exact-fix error, and per-kit command execution by kind.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from ecp_toolkit import cli, config, manifest

MANIFEST = manifest.MANIFEST_NAME
PASSTHROUGH_TOML = '[passthrough]\nsummary = "the kit\'s own CLI"\nargv = ["kitcli"]\n'
SHELL_CMDS_TOML = """\
[[command]]
name = "hello"
summary = "say hello"
kind = "shell"
argv = ["echo", "hello"]

[[command]]
name = "fwd"
summary = "forward extra arguments"
kind = "shell"
argv = ["echo"]
passthrough = true
"""


@pytest.fixture
def repos(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A repos root with two kits; ECP_REPOS_ROOT and ECP_CONFIG pointed at it."""
    root = tmp_path / "repos"
    root.mkdir()
    monkeypatch.setenv("ECP_REPOS_ROOT", str(root))
    monkeypatch.setenv("ECP_CONFIG", str(tmp_path / "cfg.json"))
    monkeypatch.chdir(tmp_path)
    return root


def _kit(root: Path, name: str, toml: str) -> Path:
    checkout = root / name
    checkout.mkdir(parents=True, exist_ok=True)
    (checkout / MANIFEST).write_text(toml, encoding="utf-8")
    return checkout


def _run_ecp(argv: list[str]) -> int:
    sys.argv = ["ecp", *argv]
    return cli.main()


# ── fleet commands ───────────────────────────────────────────────────────────


def test_build_parser_requires_a_command(repos: Path, capsys):
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args([])
    assert "required" in capsys.readouterr().err


def test_setup_writes_the_config_with_repos_root(repos: Path):
    assert _run_ecp(["setup", "--repos-root", str(repos)]) == 0
    data = json.loads(config.config_path().read_text())
    assert data["repos"]["root"] == str(repos)


def test_setup_writes_config_mode_600(repos: Path):
    _run_ecp(["setup", "--repos-root", str(repos)])
    path = config.config_path()
    assert (path.stat().st_mode & 0o777) == 0o600


def test_setup_seeds_one_kit_section(repos: Path):
    _run_ecp(["setup", "--kit", "repo-guards", "--root", str(repos / "repo-guards")])
    data = json.loads(config.config_path().read_text())
    assert data["kits"]["repo-guards"]["root"] == str(repos / "repo-guards")


def test_setup_is_idempotent_and_keeps_other_sections(repos: Path):
    _run_ecp(["setup", "--kit", "repo-guards", "--root", "/tmp/a"])
    _run_ecp(["setup", "--kit", "actions-runner", "--root", "/tmp/b"])
    data = json.loads(config.config_path().read_text())
    assert data["kits"] == {
        "repo-guards": {"root": "/tmp/a"},
        "actions-runner": {"root": "/tmp/b"},
    }


def test_doctor_reports_the_repos_root_and_each_kit(repos: Path, capsys):
    _kit(repos, "repo-guards", PASSTHROUGH_TOML)
    _kit(repos, "op-safe", SHELL_CMDS_TOML)
    assert _run_ecp(["doctor"]) == 0
    out = capsys.readouterr().out
    assert "repo-guards: passthrough -> ['kitcli']" in out
    assert "op-safe: hello, fwd" in out
    assert "actions-runner: absent" in out


def test_doctor_without_a_repos_root_carries_the_fix(repos: Path, monkeypatch, capsys):
    monkeypatch.delenv("ECP_REPOS_ROOT", raising=False)
    assert _run_ecp(["doctor"]) == 1
    out = capsys.readouterr().out
    assert "no repos root configured" in out
    assert "ecp setup --repos-root" in out
    assert "ECP_REPOS_ROOT" in out


def test_doctor_says_when_a_kit_ships_no_manifest(repos: Path, capsys):
    (repos / "op-safe").mkdir()
    _run_ecp(["setup", "--repos-root", str(repos)])
    capsys.readouterr()  # drop setup's "wrote ..." line
    assert _run_ecp(["doctor"]) == 0
    assert "op-safe: present, ships no manifest" in capsys.readouterr().out


def test_doctor_fails_loud_on_a_malformed_manifest(repos: Path):
    _kit(repos, "op-safe", "[[command]\nname = broken")
    with pytest.raises(SystemExit, match="invalid command manifest") as excinfo:
        _run_ecp(["doctor"])
    assert "op-safe" in str(excinfo.value)


def test_doctor_json_carries_per_kit_declarations(repos: Path, capsys):
    _kit(repos, "repo-guards", PASSTHROUGH_TOML)
    assert _run_ecp(["doctor", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["kits"]["repo-guards"]["manifest"]["shape"] == "passthrough"
    assert data["kits"]["repo-guards"]["manifest"]["argv"] == ["kitcli"]


def test_catalog_prints_one_row_per_kit(repos: Path, capsys):
    assert _run_ecp(["catalog"]) == 0
    out = capsys.readouterr().out
    for kit in config.KITS:
        assert kit in out


def test_status_prints_one_row_per_kit(repos: Path, capsys):
    (repos / "repo-guards").mkdir()  # present, no manifest, no pyproject
    assert _run_ecp(["status"]) == 0
    out = capsys.readouterr().out
    assert "repo-guards" in out
    assert "actions-runner" in out


def test_status_without_repos_root_prints_the_fix(repos: Path, monkeypatch, capsys):
    monkeypatch.delenv("ECP_REPOS_ROOT", raising=False)
    assert _run_ecp(["status"]) == 1
    assert "ecp setup --repos-root" in capsys.readouterr().out


# ── init / pull / vendor check (the project lane) ────────────────────────────


def test_init_scaffolds_the_one_layout(repos: Path, tmp_path: Path, capsys):
    assert _run_ecp(["init", "my-project"]) == 0
    root = tmp_path / "my-project"
    assert (root / ".ecp" / "config.json").is_file()
    assert (root / "vendor").is_dir()
    assert (root / "overlays").is_dir()
    assert "initialized project" in capsys.readouterr().out


def test_init_bare_uses_the_current_directory(repos: Path, tmp_path: Path):
    import os

    (tmp_path / "ops").mkdir()
    os.chdir(tmp_path / "ops")
    assert _run_ecp(["init"]) == 0
    assert (tmp_path / "ops" / ".ecp" / "config.json").is_file()


def test_init_refuses_an_existing_record(repos: Path, tmp_path: Path, capsys):
    _run_ecp(["init", "my-project"])
    assert _run_ecp(["init", "my-project"]) == 1
    assert "already a project" in capsys.readouterr().err


def _git(argv: list[str], cwd: Path) -> subprocess.CompletedProcess:
    """Run git, with an identity in place for the commands that need one.

    A commit needs a user.name and user.email. A developer machine has a
    global identity, so the tests passed there. A CI runner has none, so
    every commit failed, and the drift test then saw a dirty worktree
    instead of the moved HEAD it was written to prove. The identity is
    set on the repository, so it does not depend on the machine.
    """
    if argv[:1] == ["commit"]:
        for key, value in (("user.email", "t@example.com"), ("user.name", "t")):
            subprocess.run(
                ["git", "config", key, value],
                cwd=cwd,
                capture_output=True,
                text=True,
                check=False,
            )
    return subprocess.run(["git", *argv], cwd=cwd, capture_output=True, text=True, check=False)


@pytest.fixture
def upstream_source(tmp_path: Path) -> Path:
    """A real git repo with one tag: the pull target."""
    src = tmp_path / "src"
    src.mkdir()
    _git(["init", "-q"], src)
    _git(["config", "user.email", "t@example.com"], src)
    _git(["config", "user.name", "t"], src)
    (src / "SKILL.md").write_text("kit file", encoding="utf-8")
    _git(["add", "-A"], src)
    _git(["commit", "-q", "-m", "init"], src)
    _git(["tag", "-a", "v0.1.0", "-m", "v0.1.0"], src)
    return src


@pytest.fixture
def project_root(repos: Path, tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    root.mkdir()
    _run_ecp(["init", "proj"])
    import os

    os.chdir(root)
    return root


def test_pull_vendors_from_a_local_clone_source(
    repos: Path, project_root: Path, upstream_source: Path, monkeypatch
):
    # Point the kit's repo name resolution at the local source: pull is the
    # same code path git uses, just with a local URL under test.
    monkeypatch.setattr("ecp_toolkit.project.repo_url", lambda kit: str(upstream_source))
    assert _run_ecp(["pull", "op-safe", "--tag", "v0.1.0"]) == 0
    vendored = project_root / "vendor" / "op-safe"
    assert (vendored / "SKILL.md").is_file()
    meta = json.loads((vendored / ".ecp-vendor.json").read_text())
    assert meta["tag"] == "v0.1.0"
    assert meta["repo"] == "op-safe"
    record = json.loads((project_root / ".ecp" / "config.json").read_text())
    assert record["kits"]["op-safe"]["tag"] == "v0.1.0"


def test_pull_refuses_an_untagged_release(repos: Path, project_root: Path, upstream_source: Path, monkeypatch, capfd):
    monkeypatch.setattr("ecp_toolkit.project.repo_url", lambda kit: str(upstream_source))
    assert _run_ecp(["pull", "op-safe", "--tag", "v9.9.9"]) == 1
    err = capfd.readouterr().err
    assert "v9.9.9" in err
    assert "not found" in err


def test_pull_requires_the_tag(repos: Path, project_root: Path):
    sys.argv = ["ecp", "pull", "op-safe"]
    parser = cli.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["pull", "op-safe"])


def test_pull_refuses_an_unknown_kit(repos: Path, project_root: Path, capsys):
    assert _run_ecp(["pull", "not-a-kit", "--tag", "v0.1.0"]) == 1
    assert "unknown kit" in capsys.readouterr().err


def test_vendor_check_passes_a_clean_tree(
    repos: Path, project_root: Path, upstream_source: Path, monkeypatch, capsys
):
    monkeypatch.setattr("ecp_toolkit.project.repo_url", lambda kit: str(upstream_source))
    _run_ecp(["pull", "op-safe", "--tag", "v0.1.0"])
    assert _run_ecp(["vendor", "check"]) == 0
    assert "vendor check: ok" in capsys.readouterr().out


def test_vendor_check_refuses_an_edited_vendored_file(
    repos: Path, project_root: Path, upstream_source: Path, monkeypatch, capfd
):
    monkeypatch.setattr("ecp_toolkit.project.repo_url", lambda kit: str(upstream_source))
    _run_ecp(["pull", "op-safe", "--tag", "v0.1.0"])
    vendored = project_root / "vendor" / "op-safe"
    (vendored / "SKILL.md").write_text("edited in place", encoding="utf-8")
    assert _run_ecp(["vendor", "check"]) == 1
    captured = capfd.readouterr()
    assert "vendored copy is modified" in captured.err
    assert "SKILL.md" in captured.err
    assert "DRIFTED" in captured.out


def test_pull_refuses_drift_without_the_flag(
    repos: Path, project_root: Path, upstream_source: Path, monkeypatch, capfd
):
    monkeypatch.setattr("ecp_toolkit.project.repo_url", lambda kit: str(upstream_source))
    _run_ecp(["pull", "op-safe", "--tag", "v0.1.0"])
    vendored = project_root / "vendor" / "op-safe"
    (vendored / "SKILL.md").write_text("edited in place", encoding="utf-8")
    assert _run_ecp(["pull", "op-safe", "--tag", "v0.1.0"]) == 1
    assert "local changes" in capfd.readouterr().err


def test_pull_re_vendors_with_the_recorded_override(
    repos: Path, project_root: Path, upstream_source: Path, monkeypatch, capsys
):
    monkeypatch.setattr("ecp_toolkit.project.repo_url", lambda kit: str(upstream_source))
    _run_ecp(["pull", "op-safe", "--tag", "v0.1.0"])
    vendored = project_root / "vendor" / "op-safe"
    (vendored / "SKILL.md").write_text("edited in place", encoding="utf-8")
    assert _run_ecp(["pull", "op-safe", "--tag", "v0.1.0", "--allow-local-changes"]) == 0
    record = json.loads((project_root / ".ecp" / "config.json").read_text())
    overrides = record["state"]["overrides"]
    assert overrides and overrides[0]["kit"] == "op-safe"
    assert "vendored op-safe" in capsys.readouterr().out


def test_pull_detects_head_drift(
    repos: Path, project_root: Path, upstream_source: Path, monkeypatch, capfd
):
    monkeypatch.setattr("ecp_toolkit.project.repo_url", lambda kit: str(upstream_source))
    _run_ecp(["pull", "op-safe", "--tag", "v0.1.0"])
    vendored = project_root / "vendor" / "op-safe"
    # A commit past the tag moves HEAD away from the provenance commit.
    (vendored / "NEW.md").write_text("extra", encoding="utf-8")
    _git(["add", "-A"], vendored)
    _git(["commit", "-q", "-m", "drift"], vendored)
    assert _run_ecp(["vendor", "check", "op-safe"]) == 1
    assert "vendored HEAD" in capfd.readouterr().err


def test_project_commands_refuse_outside_a_project(repos: Path, tmp_path: Path, capfd):
    import os

    os.chdir(tmp_path)
    assert _run_ecp(["pull", "op-safe", "--tag", "v0.1.0"]) == 1
    assert "not a consumer project" in capfd.readouterr().err
    assert _run_ecp(["vendor", "check"]) == 1
    assert "not a consumer project" in capfd.readouterr().err


# ── mounting: repo presence is the signal ────────────────────────────────────


def test_a_fresh_ecp_only_clone_mounts_nothing(repos: Path):
    from ecp_toolkit.cli import build_parser

    parser = build_parser()
    sub = parser._subparsers._group_actions[0]  # noqa: SLF001 - the pinned shape
    assert set(sub.choices).isdisjoint(config.KITS)


def test_the_mount_offers_exactly_the_declared_commands(repos: Path):
    _kit(repos, "op-safe", SHELL_CMDS_TOML)
    parser = cli.build_parser()
    sub = parser._subparsers._group_actions[0]  # noqa: SLF001
    group = sub.choices["op-safe"]
    child = group._subparsers._group_actions[0]  # noqa: SLF001
    assert set(child.choices) == {"hello", "fwd"}


def test_mount_raises_on_a_malformed_manifest(repos: Path):
    _kit(repos, "op-safe", "[[command]]\nname = 'x'\nsummary = 'x'\nkind = 'warp'\nargv = ['x']\n")
    with pytest.raises(SystemExit, match="invalid command manifest"):
        cli.build_parser()


def test_mount_passthrough_group_takes_remainder(repos: Path):
    _kit(repos, "repo-guards", PASSTHROUGH_TOML)
    parser = cli.build_parser()
    sub = parser._subparsers._group_actions[0]  # noqa: SLF001
    assert "repo-guards" in sub.choices


# ── dispatch: each kind runs the argv it declared ────────────────────────────


def test_shell_kind_runs_the_declared_argv(repos: Path, capfd):
    _kit(repos, "op-safe", SHELL_CMDS_TOML)
    assert _run_ecp(["--fleet", "op-safe", "hello"]) == 0
    assert "hello" in capfd.readouterr().out


def test_shell_kind_forwards_extra_args_when_passthrough_true(repos: Path, capfd):
    _kit(repos, "op-safe", SHELL_CMDS_TOML)
    assert _run_ecp(["--fleet", "op-safe", "fwd", "one", "--flag=two"]) == 0
    assert "one --flag=two" in capfd.readouterr().out


def test_python_kind_invokes_uv_run_python(repos: Path, capfd):
    toml = """\
[[command]]
name = "script"
summary = "run a kit entry point"
kind = "python"
argv = ["scripts/tool.py"]
"""
    checkout = _kit(repos, "agent-workspace-kit", toml)
    (checkout / "scripts").mkdir()
    tool = checkout / "scripts" / "tool.py"
    tool.write_text(
        "import pathlib; print('ran from', pathlib.Path('scripts/tool.py').resolve())", encoding="utf-8"
    )
    assert _run_ecp(["--fleet", "agent-workspace-kit", "script"]) == 0
    out = capfd.readouterr().out
    assert "ran from" in out
    assert str(tool.resolve()) in out


def test_python_kind_refuses_extra_args_without_the_passthrough_flag(repos: Path):
    # Only a passthrough command forwards extra arguments; anything else has
    # no escape hatch, so unknown args are an error (the mtk semantic).
    toml = """\
[[command]]
name = "script"
summary = "run a kit entry point"
kind = "python"
argv = ["scripts/tool.py"]
"""
    checkout = _kit(repos, "agent-workspace-kit", toml)
    (checkout / "scripts").mkdir()
    (checkout / "scripts" / "tool.py").write_text("print('x')", encoding="utf-8")
    assert checkout.is_dir()  # the kit exists; the error fires at parse time
    with pytest.raises(SystemExit):
        _run_ecp(["--fleet", "agent-workspace-kit", "script", "surprise"])


def test_probe_kind_runs_the_declared_probe_argv(repos: Path, capfd):
    toml = """\
[[command]]
name = "health"
summary = "kit presence"
kind = "probe"
argv = ["true"]
"""
    _kit(repos, "op-safe", toml)
    assert _run_ecp(["--fleet", "op-safe", "health"]) == 0
    assert "op-safe probe status=ok" in capfd.readouterr().out


def test_probe_kind_defaults_to_presence(repos: Path, capfd):
    toml = """\
[[command]]
name = "health"
summary = "kit presence"
kind = "probe"
"""
    checkout = _kit(repos, "op-safe", toml)
    assert (checkout / manifest.MANIFEST_NAME).is_file()  # the manifest ships
    assert _run_ecp(["--fleet", "op-safe", "health"]) == 0
    captured = capfd.readouterr()
    assert "probe status=present" in (captured.out + captured.err)
    assert str(checkout) in (captured.out + captured.err)


def test_probe_kind_reports_a_failed_probe(repos: Path, capsys):
    toml = """\
[[command]]
name = "health"
summary = "kit presence"
kind = "probe"
argv = ["false"]
"""
    _kit(repos, "op-safe", toml)
    assert _run_ecp(["--fleet", "op-safe", "health"]) == 1
    assert "probe status=failed (exit 1)" in capsys.readouterr().out


def test_passthrough_group_delegates_argv_verbatim(repos: Path, monkeypatch):
    _kit(repos, "repo-guards", PASSTHROUGH_TOML)
    seen: dict[str, object] = {}

    class Proc:
        returncode = 0

    def fake_run(argv, **kw):
        seen["argv"], seen["cwd"] = argv, kw.get("cwd")
        return Proc()

    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    assert _run_ecp(["--fleet", "repo-guards", "check", ".", "--except", "ci"]) == 0
    assert seen["argv"] == ["kitcli", "check", ".", "--except", "ci"]
    assert str(seen["cwd"]).endswith("repo-guards")


def test_fleet_mode_ignores_a_project_cwd(repos: Path, tmp_path: Path):
    import os

    project_root = tmp_path / "proj"
    project_root.mkdir()
    _run_ecp(["init", "proj"])
    os.chdir(project_root)
    # --fleet keeps us in fleet mode even from inside a project; op-safe is
    # not vendored there, so the fleet checkout under repos/ is the one used.
    _kit(repos, "op-safe", SHELL_CMDS_TOML)
    assert _run_ecp(["--fleet", "op-safe", "hello"]) == 0


def test_project_mode_runs_the_vendored_copy(
    repos: Path, project_root: Path, upstream_source: Path, monkeypatch, capfd
):
    monkeypatch.setattr("ecp_toolkit.project.repo_url", lambda kit: str(upstream_source))
    _run_ecp(["pull", "op-safe", "--tag", "v0.1.0"])
    vendored = project_root / "vendor" / "op-safe"
    (vendored / MANIFEST).write_text(
        """\
[[command]]
name = "cat"
summary = "print the vendored file"
kind = "shell"
argv = ["sh", "-c", "pwd; cat SKILL.md"]
""",
        encoding="utf-8",
    )
    # No repos root at all: the project must not fall back to one.
    monkeypatch.delenv("ECP_REPOS_ROOT", raising=False)
    assert _run_ecp(["op-safe", "cat"]) == 0
    out = capfd.readouterr().out
    assert "kit file" in out
    assert str(vendored) in out


def test_project_mode_never_falls_back_to_a_shared_checkout(repos: Path, project_root: Path, monkeypatch, capfd):
    # op-safe IS checked out in fleet repos/, and NOT vendored in the project:
    # the vendor boundary means the shared checkout never runs for it. There
    # is no group to dispatch (mounts nothing), so argparse errors.
    _kit(repos, "op-safe", SHELL_CMDS_TOML)
    monkeypatch.delenv("ECP_REPOS_ROOT", raising=False)
    with pytest.raises(SystemExit):
        _run_ecp(["op-safe", "hello"])
    assert "invalid choice" in capfd.readouterr().err


# ── the config gate ──────────────────────────────────────────────────────────


def test_requires_gate_errors_with_the_exact_fix(repos: Path, monkeypatch, capfd):
    toml = """\
[[command]]
name = "read"
summary = "read an item"
kind = "shell"
argv = ["echo"]
requires = ["account"]
"""
    _kit(repos, "op-safe", toml)
    assert _run_ecp(["--fleet", "op-safe", "read"]) == 2
    err = capfd.readouterr().err
    assert "op-safe is not configured: missing account" in err
    assert "ECP_OP_SAFE_ACCOUNT" in err
    assert "ecp setup" in err


def test_requires_gate_passes_when_the_key_resolves(repos: Path, capfd):
    toml = """\
[[command]]
name = "read"
summary = "read an item"
kind = "shell"
argv = ["echo", "the gate passed"]
requires = ["account"]
"""
    _kit(repos, "op-safe", toml)
    config_path = config.config_path()
    config_path.write_text(json.dumps({"kits": {"op-safe": {"account": "me"}}}), encoding="utf-8")
    assert _run_ecp(["--fleet", "op-safe", "read"]) == 0
    assert "the gate passed" in capfd.readouterr().out


def test_root_key_resolves_from_the_env_override(repos: Path, monkeypatch, tmp_path: Path):
    monkeypatch.delenv("ECP_REPOS_ROOT", raising=False)
    monkeypatch.setenv("ECP_OP_SAFE_ROOT", str(tmp_path / "op-safe-elsewhere"))
    (tmp_path / "op-safe-elsewhere").mkdir()
    assert config.kit_root("op-safe") == tmp_path / "op-safe-elsewhere"


def test_env_override_wins_over_the_config_file(repos: Path, monkeypatch, tmp_path: Path):
    config_path = config.config_path()
    config_path.write_text(
        json.dumps({"kits": {"op-safe": {"root": "/tmp/from-file"}}}), encoding="utf-8"
    )
    monkeypatch.setenv("ECP_OP_SAFE_ROOT", str(tmp_path / "from-env"))
    (tmp_path / "from-env").mkdir()
    assert config.kit_root("op-safe") == tmp_path / "from-env"
