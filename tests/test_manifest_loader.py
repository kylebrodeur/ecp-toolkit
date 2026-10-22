"""Tests for the per-kit command manifest loader (ecp_toolkit/manifest.py).

The loader is the design's fail-closed point: every validation rule named in
docs/CLI-DESIGN.md "Validation" has a test here that proves the rule fires,
with the manifest path in the message. The mount behavior (what `ecp <kit>`
offers) is pinned by tests/test_cli_fleet.py and tests/test_cli_mount.py.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ecp_toolkit import manifest


def _write_manifest(root: Path, kit: str, body: str) -> Path:
    checkout = root / kit
    checkout.mkdir(parents=True, exist_ok=True)
    path = checkout / manifest.MANIFEST_NAME
    path.write_text(body, encoding="utf-8")
    return path


def _error_args(exc: pytest.ExceptionInfo) -> tuple[str, str]:
    manifest_file, message = exc.value.args
    return str(manifest_file), message


# ── presence / parsing ───────────────────────────────────────────────────────


def test_load_returns_none_without_a_manifest(tmp_path: Path):
    checkout = tmp_path / "repo-guards"
    checkout.mkdir()
    assert manifest.load(checkout) is None


def test_load_rejects_invalid_toml(tmp_path: Path):
    _write_manifest(tmp_path, "repo-guards", "[[command]\nname = broken")
    with pytest.raises(manifest.CommandManifestError, match="invalid TOML") as exc:
        manifest.load(tmp_path / "repo-guards")
    manifest_file, message = _error_args(exc)
    assert manifest_file.endswith("ecp-commands.toml")
    assert "invalid TOML" in message


def test_manifest_path_is_the_repo_root(tmp_path: Path):
    assert manifest.manifest_path(tmp_path) == tmp_path / "ecp-commands.toml"


# ── shape: either commands or passthrough, never both, never neither ────────


def test_load_rejects_commands_and_passthrough_together(tmp_path: Path):
    _write_manifest(
        tmp_path,
        "omp-rpc-cli",
        """\
[passthrough]
summary = "the omp-rpc CLI"
argv = ["omp-rpc"]

[[command]]
name = "sessions"
summary = "list sessions"
kind = "shell"
argv = ["sessions"]
""",
    )
    with pytest.raises(manifest.CommandManifestError, match="not both") as exc:
        manifest.load(tmp_path / "omp-rpc-cli")
    manifest_file, _ = _error_args(exc)
    assert manifest_file.endswith("ecp-commands.toml")


def test_load_rejects_neither_commands_nor_passthrough(tmp_path: Path):
    _write_manifest(tmp_path, "op-safe", '[defaults]\nkind = "shell"\n')
    with pytest.raises(
        manifest.CommandManifestError, match=r"missing \[\[command\]\] entries or a \[passthrough\]"
    ) as exc:
        manifest.load(tmp_path / "op-safe")
    _error_args(exc)


# ── command fields: name, summary, kind ──────────────────────────────────────


def test_load_rejects_a_command_missing_a_name(tmp_path: Path):
    _write_manifest(
        tmp_path,
        "op-safe",
        """\
[[command]]
summary = "read an item"
kind = "shell"
argv = ["scripts/op-access.sh", "read"]
""",
    )
    with pytest.raises(manifest.CommandManifestError, match="missing a non-empty name"):
        manifest.load(tmp_path / "op-safe")


def test_load_rejects_an_empty_name(tmp_path: Path):
    _write_manifest(
        tmp_path,
        "op-safe",
        """\
[[command]]
name = ""
summary = "read an item"
kind = "shell"
argv = ["op-access.sh"]
""",
    )
    with pytest.raises(manifest.CommandManifestError, match="missing a non-empty name"):
        manifest.load(tmp_path / "op-safe")


def test_load_rejects_a_command_missing_a_summary(tmp_path: Path):
    _write_manifest(
        tmp_path,
        "op-safe",
        """\
[[command]]
name = "read"
kind = "shell"
argv = ["op-access.sh", "read"]
""",
    )
    with pytest.raises(manifest.CommandManifestError, match="missing a non-empty summary"):
        manifest.load(tmp_path / "op-safe")


def test_load_rejects_a_command_missing_a_kind(tmp_path: Path):
    _write_manifest(
        tmp_path,
        "op-safe",
        """\
[[command]]
name = "read"
summary = "read an item"
argv = ["op-access.sh"]
""",
    )
    with pytest.raises(manifest.CommandManifestError, match="missing a non-empty kind"):
        manifest.load(tmp_path / "op-safe")


def test_load_names_the_command_in_the_summary_error(tmp_path: Path):
    _write_manifest(
        tmp_path,
        "op-safe",
        """\
[[command]]
name = "read"
kind = "shell"
argv = ["op-access.sh", "read"]
""",
    )
    with pytest.raises(manifest.CommandManifestError, match="command 'read' is missing") as exc:
        manifest.load(tmp_path / "op-safe")
    manifest_file, _ = _error_args(exc)
    # The message names the manifest and the problem (the fail-closed contract).
    assert manifest_file.endswith("ecp-commands.toml")


# ── the kind vocabulary is closed ────────────────────────────────────────────


def test_the_kind_vocabulary_is_the_designs_three_kinds():
    assert manifest.KINDS == ("shell", "python", "probe")


def test_load_rejects_an_unknown_kind(tmp_path: Path):
    _write_manifest(
        tmp_path,
        "agent-workspace-kit",
        """\
[[command]]
name = "launch"
summary = "launch the team"
kind = "teleport"
argv = ["scripts/launch.sh"]
""",
    )
    with pytest.raises(manifest.CommandManifestError, match="unknown kind 'teleport'") as exc:
        manifest.load(tmp_path / "agent-workspace-kit")
    manifest_file, _ = _error_args(exc)
    assert manifest_file.endswith("ecp-commands.toml")


def test_load_names_the_supported_kinds_in_the_error(tmp_path: Path):
    _write_manifest(
        tmp_path,
        "agent-workspace-kit",
        """\
[[command]]
name = "launch"
summary = "launch the team"
kind = "docker"
argv = ["scripts/launch.sh"]
""",
    )
    with pytest.raises(manifest.CommandManifestError, match="supported: ..shell., .python., .probe.") as exc:
        manifest.load(tmp_path / "agent-workspace-kit")
    _error_args(exc)


# ── argv requirements per kind ───────────────────────────────────────────────


@pytest.mark.parametrize("kind", ["shell", "python"])
def test_load_rejects_arg_kinds_without_argv(tmp_path: Path, kind: str):
    _write_manifest(
        tmp_path,
        "op-safe",
        f"""\
[[command]]
name = "read"
summary = "read an item"
kind = "{kind}"
""",
    )
    with pytest.raises(manifest.CommandManifestError, match="requires a non-empty argv"):
        manifest.load(tmp_path / "op-safe")


def test_load_accepts_probe_without_argv(tmp_path: Path):
    # probe is the health/presence check: argv is optional, presence is the fallback.
    _write_manifest(
        tmp_path,
        "op-safe",
        """\
[[command]]
name = "health"
summary = "presence check"
kind = "probe"
""",
    )
    loaded = manifest.load(tmp_path / "op-safe")
    assert loaded is not None
    assert loaded.commands[0].kind == "probe"
    assert loaded.commands[0].argv == ()


# ── field types ──────────────────────────────────────────────────────────────


def test_load_rejects_a_non_string_requires(tmp_path: Path):
    _write_manifest(
        tmp_path,
        "op-safe",
        """\
[[command]]
name = "read"
summary = "read an item"
kind = "shell"
argv = ["op-access.sh"]
requires = ["op_account", 3]
""",
    )
    with pytest.raises(manifest.CommandManifestError, match="must be a list of strings"):
        manifest.load(tmp_path / "op-safe")


def test_load_rejects_a_requires_that_is_not_a_list(tmp_path: Path):
    _write_manifest(
        tmp_path,
        "op-safe",
        """\
[[command]]
name = "read"
summary = "read an item"
kind = "shell"
argv = ["op-access.sh"]
requires = "op_account"
""",
    )
    with pytest.raises(manifest.CommandManifestError, match="must be a list of strings"):
        manifest.load(tmp_path / "op-safe")


def test_load_rejects_a_non_integer_timeout(tmp_path: Path):
    _write_manifest(
        tmp_path,
        "op-safe",
        """\
[[command]]
name = "read"
summary = "read an item"
kind = "shell"
argv = ["op-access.sh"]
timeout = "tirty seconds"
""",
    )
    with pytest.raises(manifest.CommandManifestError, match="timeout must be an integer"):
        manifest.load(tmp_path / "op-safe")


def test_load_accepts_an_integer_timeout(tmp_path: Path):
    _write_manifest(
        tmp_path,
        "op-safe",
        """\
[[command]]
name = "read"
summary = "read an item"
kind = "shell"
argv = ["op-access.sh"]
timeout = 30
""",
    )
    loaded = manifest.load(tmp_path / "op-safe")
    assert loaded is not None and loaded.commands[0].timeout == 30


def test_load_rejects_a_non_boolean_passthrough_flag(tmp_path: Path):
    _write_manifest(
        tmp_path,
        "op-safe",
        """\
[[command]]
name = "read"
summary = "read an item"
kind = "shell"
argv = ["op-access.sh"]
passthrough = "yes"
""",
    )
    with pytest.raises(manifest.CommandManifestError, match="passthrough must be a boolean"):
        manifest.load(tmp_path / "op-safe")


# ── defaults merge (the command's own value wins) ────────────────────────────


def test_load_merges_defaults_and_the_command_value_wins(tmp_path: Path):
    _write_manifest(
        tmp_path,
        "agent-workspace-kit",
        """\
[defaults]
kind = "shell"
requires = ["root"]

[[command]]
name = "launch"
summary = "launch the team"
argv = ["scripts/launch.sh"]
requires = ["team_config"]

[[command]]
name = "stop"
summary = "stop the team"
argv = ["scripts/stop.sh"]
""",
    )
    loaded = manifest.load(tmp_path / "agent-workspace-kit")
    assert loaded is not None
    launch, stop = loaded.commands
    assert launch.kind == "shell"
    assert launch.requires == ("team_config",)  # the command's own value wins
    assert stop.requires == ("root",)  # the default fills in
    assert stop.kind == "shell"


def test_load_rejects_a_defaults_that_is_not_a_table(tmp_path: Path):
    _write_manifest(tmp_path, "op-safe", 'defaults = "not a table"\n')
    with pytest.raises(manifest.CommandManifestError, match=r"\[defaults\] must be a table") as exc:
        manifest.load(tmp_path / "op-safe")
    _error_args(exc)


def test_load_rejects_an_empty_commands_list(tmp_path: Path):
    _write_manifest(tmp_path, "op-safe", "command = []\n")
    with pytest.raises(manifest.CommandManifestError, match="non-empty list"):
        manifest.load(tmp_path / "op-safe")


def test_load_rejects_a_command_that_is_not_a_table(tmp_path: Path):
    _write_manifest(tmp_path, "op-safe", 'command = ["read"]\n')
    with pytest.raises(manifest.CommandManifestError, match="must be a table"):
        manifest.load(tmp_path / "op-safe")


# ── the whole-surface passthrough shape ──────────────────────────────────────


def test_load_parses_a_passthrough_surface(tmp_path: Path):
    _write_manifest(
        tmp_path,
        "repo-guards",
        """\
[passthrough]
summary = "the guv CLI already owns this surface"
argv = ["guv"]
""",
    )
    loaded = manifest.load(tmp_path / "repo-guards")
    assert loaded is not None and loaded.commands == []
    assert loaded.passthrough is not None
    assert loaded.passthrough.argv == ("guv",)
    assert loaded.passthrough.summary == "the guv CLI already owns this surface"


def test_load_rejects_a_passthrough_without_argv(tmp_path: Path):
    _write_manifest(tmp_path, "repo-guards", '[passthrough]\nsummary = "the guv CLI"\n')
    with pytest.raises(manifest.CommandManifestError, match=r"\[passthrough\] requires a non-empty argv"):
        manifest.load(tmp_path / "repo-guards")


def test_load_rejects_a_passthrough_without_a_summary(tmp_path: Path):
    _write_manifest(tmp_path, "repo-guards", '[passthrough]\nargv = ["guv"]\n')
    with pytest.raises(manifest.CommandManifestError, match=r"\[passthrough\] requires a non-empty summary"):
        manifest.load(tmp_path / "repo-guards")


def test_load_rejects_a_non_string_passthrough_requires(tmp_path: Path):
    _write_manifest(
        tmp_path,
        "repo-guards",
        """\
[passthrough]
summary = "guv"
argv = ["guv"]
requires = [42]
""",
    )
    with pytest.raises(manifest.CommandManifestError, match="must be a list of strings"):
        manifest.load(tmp_path / "repo-guards")


def test_passthrough_requires_is_optional(tmp_path: Path):
    _write_manifest(
        tmp_path,
        "repo-guards",
        """\
[passthrough]
summary = "guv"
argv = ["guv"]
requires = ["owner"]
""",
    )
    loaded = manifest.load(tmp_path / "repo-guards")
    assert loaded is not None and loaded.passthrough is not None
    assert loaded.passthrough.requires == ("owner",)


# ── discovery: repo presence is the signal ───────────────────────────────────


def test_discover_finds_kits_that_ship_a_manifest(tmp_path: Path):
    _write_manifest(tmp_path, "repo-guards", '[passthrough]\nsummary = "guv"\nargv = ["guv"]\n')
    (tmp_path / "actions-runner").mkdir()
    (tmp_path / "not-a-kit").write_text("a file, not a dir", encoding="utf-8")
    found = manifest.discover(tmp_path)
    assert set(found) == {"repo-guards"}
    assert found["repo-guards"] == tmp_path / "repo-guards"


def test_discover_over_a_missing_root_mounts_nothing(tmp_path: Path):
    assert manifest.discover(tmp_path / "exists-not") == {}
