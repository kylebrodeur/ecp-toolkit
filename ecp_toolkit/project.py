"""Consumer projects: the record, init, pull, and the drift guard.

The one layout (docs/VENDOR-MODEL.md, "Layout (the only layout)"):

```
<project>/
  .ecp/config.json                the project record: slug, kits, tags, state
  vendor/<kit>/                   git checkout detached at the release tag
  vendor/<kit>/.ecp-vendor.json   provenance: repo, tag, commit
  overlays/<kit>/                 everything the project decides
```

Rules carried from the vendor model:

- A vendored copy is never edited; the overlay carries the decisions.
- The upgrade unit is the upstream release TAG. ``ecp pull <kit> --tag <t>``
  (re)vendors the pinned copy.
- Drift is refused on every consume: worktree clean apart from the managed
  provenance file, HEAD equals the provenance commit, and the recorded tag
  still resolves to that commit.
- ``--allow-local-changes`` is the explicit, recorded override; it prints
  every finding, records the override in the project state, and shows up in
  ``ecp doctor``. It is never the default.
- Secrets: names are public, values are never written anywhere.

``ecp pull`` is the ONE command that writes to a consumer project.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

RECORD_DIR = ".ecp"
RECORD_FILE = "config.json"
VENDOR_DIR = "vendor"
OVERLAYS_DIR = "overlays"
VENDOR_META = ".ecp-vendor.json"
STATE_ALLOW_OVERRIDE = "allow_local_changes"

# Kit -> GitHub repo name (the family's public repos under one owner;
# catalog/INDEX.md is the authoritative table).
REPO_NAMES: dict[str, str] = {
    "ecp-toolkit": "ecp-toolkit",
    "repo-guards": "repo-guards",
    "actions-runner": "actions-runner",
    "agent-workspace-kit": "agent-workspace-kit",
    "docs-policy-kit": "docs-policy-kit",
    "op-safe": "op-safe",
    "omp-rpc-cli": "omp-rpc-cli",
}
REPO_OWNER = "kylebrodeur"


class ProjectError(Exception):
    """A refusal with the exact fix in the message."""


Runner = Callable[[list[str]], tuple[int, str]]


def record_path_of(project_root: Path) -> Path:
    """The project record path; raises when this is not a project."""
    path = Path(project_root) / RECORD_DIR / RECORD_FILE
    if not path.is_file():
        raise ProjectError(f"{Path(project_root)} is not a project. Fix: run `ecp init` here first")
    return path


def read_record(project_root: Path) -> dict[str, Any]:
    """The project record as parsed JSON."""
    return json.loads(record_path_of(project_root).read_text(encoding="utf-8"))


def repo_name(kit: str) -> str:
    """The kit's GitHub repo name; a refusal naming the family when unknown.

    ``ECP_<KIT>_REPO_URL`` may point the clone at any URL (a fork, a
    mirror, a local bare repo, an example's demo kit). It never bypasses
    the tag pin: whatever the URL, the pull checks out a release tag.
    """
    env_url = os.getenv(f"ECP_{kit.upper().replace('-', '_')}_REPO_URL", "").strip()
    if env_url:
        name = env_url.rstrip("/").split("/")[-1].removesuffix(".git")
        REPO_NAMES.setdefault(kit, name)
        return name
    try:
        return REPO_NAMES[kit]
    except KeyError:
        raise ProjectError(
            f"unknown kit {kit!r}; known kits: {', '.join(REPO_NAMES)}. "
            "A new kit is a repo plus one ecp-commands.toml manifest"
        ) from None


def repo_url(kit: str) -> str:
    """The kit's clone URL: the env override first, then the family table."""
    env_url = os.getenv(f"ECP_{kit.upper().replace('-', '_')}_REPO_URL", "").strip()
    if env_url:
        return env_url
    return f"https://github.com/{REPO_OWNER}/{repo_name(kit)}"


def _default_run(argv: list[str]) -> tuple[int, str]:
    """Run a command; return (exit code, combined output)."""
    try:
        result = subprocess.run(argv, capture_output=True, text=True, check=False, timeout=600)
    except FileNotFoundError:
        return 127, f"{argv[0]} not found"
    return result.returncode, (result.stdout + result.stderr).rstrip("\n")


def _validate_slug(slug: str) -> None:
    bad = not slug or any(c in slug for c in "/\\ ") or slug != slug.lower()
    if bad:
        raise ProjectError(
            f"project id {slug!r} cannot form a project directory or app name. "
            "Use lowercase letters, digits, dots, dashes, and underscores"
        )


def init_project(base: Path, project_id: str | None = None) -> Path:
    """Scaffold a consumer project: the record, the vendor dir, the overlays dir.

    Bare: ``base`` is the project. Named: ``base/<id>`` is. Pure local
    scaffold: no network, no account access, nothing else written. Refuses
    to overwrite an existing record.
    """
    if project_id is not None:
        _validate_slug(project_id)
        root = base / project_id
        slug = project_id
    else:
        root = base
        slug = base.name
        _validate_slug(slug)

    record_path = root / RECORD_DIR / RECORD_FILE
    if record_path.exists():
        raise ProjectError(f"{record_path} already exists; this directory is already a project")

    (root / VENDOR_DIR).mkdir(parents=True, exist_ok=True)
    (root / OVERLAYS_DIR).mkdir(parents=True, exist_ok=True)
    record_path.parent.mkdir(parents=True, exist_ok=True)
    record_path.write_text(json.dumps({"slug": slug, "kits": {}}, indent=2) + "\n", encoding="utf-8")
    keep_project_git_clean(root)
    return root


def keep_project_git_clean(root: Path) -> None:
    """Ignore vendor/ inside the project's git repo.

    A nested checkout under vendor/ shows as one untracked dir in the
    parent project's git status (git does not track inside a nested repo).
    Ignoring it keeps the project clean while the drift guard still
    enforces the pin inside the nested checkout.
    """
    gitignore = root / ".gitignore"
    lines = gitignore.read_text(encoding="utf-8").splitlines() if gitignore.is_file() else []
    if "vendor/" not in lines:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append("vendor/")
        gitignore.write_text("\n".join(lines) + "\n", encoding="utf-8")


def vendor_dir(project_root: Path, kit: str) -> Path:
    """``vendor/<kit>/`` inside the project."""
    return Path(project_root) / VENDOR_DIR / kit


def overlay_dir(project_root: Path, kit: str) -> Path:
    """``overlays/<kit>/`` inside the project (the dir the consumer owns)."""
    return Path(project_root) / OVERLAYS_DIR / kit


def _tag_head(git: Runner, repo: Path, tag: str) -> str | None:
    """The commit a tag names, or None when the tag does not resolve."""
    rc, out = git(["git", "-C", str(repo), "rev-parse", "--verify", "--quiet", f"{tag}^{{commit}}"])
    return out.strip() if rc == 0 and out.strip() else None


def pull(
    project_root: Path,
    kit: str,
    *,
    tag: str,
    allow_local_changes: bool = False,
    run: Runner = _default_run,
) -> Path:
    """Vendor a tag-pinned copy into ``vendor/<kit>/``.

    The one command that writes to a consumer project. Order of operations,
    from the design: refuse drift first (unless ``allow_local_changes``, the
    explicit, recorded override), resolve the tag before any write, then
    checkout, record provenance, and merge the record entry.
    """
    record_path = record_path_of(project_root)
    record = json.loads(record_path.read_text(encoding="utf-8"))
    dest = vendor_dir(project_root, kit)

    if tag.strip() != tag or not tag:
        raise ProjectError("missing a --tag: the upgrade unit is the release tag, so every pull names one")
    name = repo_name(kit)

    if dest.exists():
        ok, findings = vendor_check(project_root, kit, git=run)
        if not ok and not allow_local_changes:
            raise ProjectError(
                f"{kit}'s vendored tree has local changes; refusing. Findings:\n"
                + "\n".join(f"  - {f}" for f in findings)
                + "\nFix: re-vendor over it after deciding, or pass --allow-local-changes "
                "(the explicit, recorded override)"
            )
        if not ok:
            record.setdefault("state", {}).setdefault("overrides", []).append(
                {"kit": kit, "override": "allow-local-changes", "findings": findings}
            )

    if dest.exists():
        if _tag_head(run, dest, tag) is None:
            rc, out = run(["git", "-C", str(dest), "fetch", "--quiet", "origin"])
            if rc != 0:
                raise ProjectError(f"git fetch failed for {kit!r}: {out}")
            if _tag_head(run, dest, tag) is None:
                raise ProjectError(f"tag {tag!r} not found for {kit!r} after fetch")
    else:
        url = repo_url(kit)
        tmp_root = Path(tempfile.mkdtemp(prefix="ecp-vendor-"))
        try:
            rc, out = run(["git", "clone", "--quiet", url, str(tmp_root / "r")])
            if rc != 0:
                raise ProjectError(f"git clone failed for {kit!r}: {out}")
            if _tag_head(run, tmp_root / "r", tag) is None:
                raise ProjectError(f"tag {tag!r} not found upstream for {kit!r}")
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(tmp_root / "r"), str(dest))
        finally:
            shutil.rmtree(tmp_root, ignore_errors=True)

    head = _tag_head(run, dest, tag)
    if head is None:
        raise ProjectError(f"tag {tag!r} went missing for {kit!r} before checkout")
    rc, out = run(["git", "-C", str(dest), "checkout", "--quiet", "--detach", head])
    if rc != 0:
        raise ProjectError(f"detaching at {tag!r} failed for {kit!r}: {out}")
    meta = {
        "repo": name,
        "tag": tag,
        "commit": head,
        "vendored": "detached checkout of the release tag",
    }
    (dest / VENDOR_META).write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

    record_kits = record.setdefault("kits", {})
    record_kits[kit] = {"vendor": f"{VENDOR_DIR}/{kit}", "tag": tag}
    record_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(f"vendored {kit}: {dest} at {tag}")
    return dest


def vendor_check(
    project_root: Path, kit: str, git: Runner = _default_run
) -> tuple[bool, list[str]]:
    """Read-only drift check for one vendored kit: ``(ok, findings)``.

    A copy passes when its HEAD equals the recorded commit, the recorded
    tag still resolves to that commit, and the worktree is clean apart from
    the managed provenance file. Findings name the offending file or fact,
    and each one ends with where the change belongs (the overlay or an
    upstream release).
    """
    dest = vendor_dir(project_root, kit)
    findings: list[str] = []
    if not dest.is_dir() or not (dest / ".git").exists():
        exists_note = "exists" if dest.exists() else "never vendored"
        return False, [
            f"{exists_note} at {dest}; not a vendored git copy. Fix: run `ecp pull {kit} --tag <release>`"
        ]
    meta_path = dest / VENDOR_META
    if not meta_path.is_file():
        return False, [
            f"{dest} has no {VENDOR_META} provenance. Fix: run `ecp pull {kit} --tag <release>`"
        ]
    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    rc, out = git(["git", "-C", str(dest), "status", "--porcelain", "-uall", "--", f":!{VENDOR_META}"])
    if rc != 0:
        return False, [f"git status failed in {dest}: {out}"]
    for line in out.splitlines():
        if not line.strip():
            continue
        # porcelain v1: XY + space + path. Slice from index 2 and lstrip the
        # path; never lstrip the whole line (that eats a leading-space X column).
        rel = line[2:].lstrip()
        if rel.startswith('"') and rel.endswith('"') and len(rel) >= 2:
            rel = rel[1:-1].encode("latin-1", "backslashreplace").decode("unicode_escape")
        if rel.endswith("/"):
            continue  # untracked dir line; -uall keeps its files as separate entries
        findings.append(
            f"vendored copy is modified: {rel} - vendor/ is not a scratch tree; "
            f"changes belong in overlays/{kit}/ or in an upstream release"
        )

    rc, out = git(["git", "-C", str(dest), "rev-parse", "HEAD"])
    if rc != 0:
        return False, [f"git rev-parse failed in {dest}: {out}"]
    head = out.strip()
    if head != meta.get("commit", ""):
        findings.append(
            f"vendored HEAD {head[:12]} != provenance commit {str(meta.get('commit', '?'))[:12]}; "
            f"fix: re-vendor with `ecp pull {kit} --tag {meta.get('tag', '?')}`"
        )

    # Commit comparison, not describe --exact-match: two tags can share one
    # commit; the right question is whether the RECORDED tag resolves to HEAD.
    rc, out = git(["git", "-C", str(dest), "rev-parse", "--verify", "--quiet", f"{meta.get('tag', '')}^{{commit}}"])
    if rc != 0 or not out.strip():
        findings.append(
            f"provenance tag {meta.get('tag', '?')!r} does not resolve in the vendored copy; "
            f"fix: re-vendor with `ecp pull {kit} --tag <release>`"
        )
    elif out.strip() != head:
        findings.append(
            f"tag {meta.get('tag', '?')!r} resolves to {out.strip()[:12]}, not HEAD; "
            f"fix: re-vendor with `ecp pull {kit} --tag {meta.get('tag', '?')}`"
        )

    return not findings, findings


def vendor_check_all(project_root: Path, git: Runner = _default_run) -> tuple[bool, list[str]]:
    """Drift check every recorded kit; also names a vendored tree with no record."""
    record = read_record(project_root)
    recorded = set(record.get("kits", {}))
    all_findings: list[str] = []
    ok = True

    for kit in sorted(recorded):
        kit_ok, findings = vendor_check(project_root, kit, git=git)
        all_findings.extend(findings)
        ok = ok and kit_ok

    if (Path(project_root) / VENDOR_DIR).is_dir():
        for child in sorted((Path(project_root) / VENDOR_DIR).iterdir()):
            if child.is_dir() and child.name not in recorded:
                all_findings.append(
                    f"{child} is vendored but not in the project record; "
                    f"fix: run `ecp pull {child.name} --tag <release>` to record it, or remove the tree"
                )
                ok = False
    return ok, all_findings


def record_override(project_root: Path, kit: str, override: str, findings: list[str]) -> None:
    """Record an explicit override in the project state (visible to doctor)."""
    record_path = record_path_of(project_root)
    record = json.loads(record_path.read_text(encoding="utf-8"))
    state = record.setdefault("state", {})
    state.setdefault("overrides", []).append({"kit": kit, "override": override, "findings": findings})
    record_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
