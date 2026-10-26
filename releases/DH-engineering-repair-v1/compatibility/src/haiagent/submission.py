"""Inspect the deliverable Git tree without changing a snapshot's Git state.

The base commit is captured once from the task root.  A copied snapshot's HEAD,
index metadata, and workspace fingerprint are not submission evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from contextlib import contextmanager
from contextvars import ContextVar
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tempfile
import time
from .executor import BASE_ENV

# Extracted from BestFGS v14; HAIAgent adds shared wall-clock enforcement.
_DEADLINE = ContextVar("submission_deadline", default=None)


@contextmanager
def submission_deadline(deadline):
    token = _DEADLINE.set(deadline)
    try:
        yield
    finally:
        _DEADLINE.reset(token)


class SubmissionError(RuntimeError):
    """A submission could not be inspected; callers must not assume success."""


@dataclass(frozen=True, slots=True)
class GitSubmission:
    base_commit: str
    patch: bytes
    changed_paths: tuple[str, ...]
    tree_id: str = ""

    @property
    def has_changes(self) -> bool:
        return bool(self.patch and self.changed_paths)

    @property
    def patch_sha256(self) -> str:
        return hashlib.sha256(self.patch).hexdigest()


_EXCLUDED_COMPONENTS = frozenset({
    ".git", "__pycache__",
})
_REPOSITORY_ENV = {
    "GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_PREFIX", "GIT_CEILING_DIRECTORIES",
}


def _environment() -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if key.upper() in BASE_ENV and key not in _REPOSITORY_ENV}
    env["GIT_OPTIONAL_LOCKS"] = "0"
    return env


def _run(
    root: Path,
    args: list[str],
    *,
    env: dict[str, str],
    input_bytes: bytes | None = None,
) -> bytes:
    try:
        remaining = 60 if _DEADLINE.get() is None else _DEADLINE.get() - time.monotonic()
        if remaining <= 0:
            raise SubmissionError("Submission deadline exhausted")
        result = subprocess.run(
            ["git", "-c", "core.fsmonitor=false", *args],
            cwd=root,
            env=env,
            input=input_bytes,
            capture_output=True,
            check=True,
            timeout=min(60, remaining),
        )
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or b"").decode("utf-8", errors="replace").strip()
        raise SubmissionError(f"Git submission inspection failed: {detail or exc.returncode}") from exc
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SubmissionError(f"Git submission inspection failed: {exc}") from exc
    return result.stdout


def _repository(workspace: Path) -> tuple[Path, list[str], dict[str, str]] | None:
    root = Path(workspace).resolve()
    if not root.is_dir():
        raise SubmissionError(f"Candidate workspace does not exist: {root}")
    # Never discover an enclosing repository when a task root is not itself Git.
    marker = root / ".git"
    if not os.path.lexists(marker):
        return None
    env = _environment()
    git_dir_text = _run(root, ["rev-parse", "--absolute-git-dir"], env=env)
    git_dir = Path(os.fsdecode(git_dir_text.rstrip(b"\r\n"))).resolve()
    # A .git file (including one copied from a worktree) may reference an external
    # Git directory.  Explicit work-tree plus a disposable index/object store keep
    # that directory read-only and bind all file reads to this candidate.
    args = [f"--git-dir={git_dir}", f"--work-tree={root}"]
    return root, args, env


def resolve_git_base(workspace: Path) -> str | None:
    """Return this task root's HEAD, or None only when it has no .git marker."""
    repo = _repository(workspace)
    if repo is None:
        return None
    root, args, env = repo
    return _run(root, [*args, "rev-parse", "--verify", "HEAD^{commit}"], env=env).decode("ascii").strip()


def _exclusions(paths: tuple[str, ...]) -> tuple[str, ...]:
    selected: list[str] = []
    for value in paths:
        path = PurePosixPath(value.replace("\\", "/"))
        if path.is_absolute() or ".." in path.parts or not path.parts or ":" in path.parts[0]:
            raise SubmissionError(f"Excluded path must be relative to the candidate: {value!r}")
        selected.append(path.as_posix())
    return tuple(selected)


def _excluded(path: str, exclusions: tuple[str, ...]) -> bool:
    parts = PurePosixPath(path).parts
    return bool(_EXCLUDED_COMPONENTS.intersection(parts)) or any(
        path == prefix or path.startswith(prefix + "/") for prefix in exclusions
    )


def _has_symlink_parent(root: Path, path: str) -> bool:
    current = root
    for part in PurePosixPath(path).parts[:-1]:
        current = current / part
        if current.is_symlink():
            return True
    return False


def inspect_git_submission(
    candidate: Path,
    base_commit: str,
    *,
    excluded_paths: tuple[str, ...] = (),
) -> GitSubmission:
    """Build the final working-tree patch against an explicit immutable base.

    Include tracked, staged, deleted, and non-ignored new files, following the
    existing Notebook export contract.  No filename guesses classify new source
    files as scratch scripts: callers can exclude explicitly owned artifacts.
    A nonempty patch says only that an artifact exists, never that it is correct.
    Git errors raise SubmissionError, while an unchanged deliverable returns an
    empty patch and empty changed_paths.
    """
    if not re.fullmatch(r"[0-9a-fA-F]{40}|[0-9a-fA-F]{64}", base_commit):
        raise SubmissionError("Submission base must be a full immutable Git commit ID")
    repo = _repository(candidate)
    if repo is None:
        raise SubmissionError("Candidate has no task-local Git repository")
    root, args, env = repo
    exclusions = _exclusions(excluded_paths)
    resolved_base = _run(
        root, [*args, "rev-parse", "--verify", f"{base_commit}^{{commit}}"], env=env,
    ).decode("ascii").strip()
    # Preserve the inclusion of explicitly staged ignored new files, too.  The
    # real index is read once but is never refreshed or written by this module.
    tracked = _run(root, [*args, "ls-files", "--cached", "-z"], env=env).split(b"\0")
    common_text = _run(root, [*args, "rev-parse", "--git-common-dir"], env=env)
    common = (root / os.fsdecode(common_text.rstrip(b"\r\n"))).resolve()
    with tempfile.TemporaryDirectory(prefix="bestfgs-submission-") as directory:
        temporary = Path(directory)
        objects = temporary / "objects"
        objects.mkdir()
        isolated_env = dict(
            env,
            GIT_INDEX_FILE=str(temporary / "index"),
            GIT_OBJECT_DIRECTORY=str(objects),
            GIT_ALTERNATE_OBJECT_DIRECTORIES=str(common / "objects"),
        )
        _run(root, [*args, "read-tree", resolved_base], env=isolated_env)
        pathspecs = ["."]
        for component in sorted(_EXCLUDED_COMPONENTS):
            pathspecs.extend([
                f":(exclude,glob)**/{component}",
                f":(exclude,glob)**/{component}/**",
            ])
        pathspecs.extend(f":(exclude,literal){path}" for path in exclusions)
        _run(root, [*args, "add", "-A", "--", *pathspecs], env=isolated_env)
        force_paths: list[bytes] = []
        for raw in tracked:
            if not raw:
                continue
            path = os.fsdecode(raw)
            if (not _excluded(path, exclusions)
                    and not _has_symlink_parent(root, path)
                    and os.path.lexists(root / path)):
                force_paths.append(raw)
        if force_paths:
            _run(
                root, [*args, "--literal-pathspecs", "add", "-f", "--pathspec-from-file=-", "--pathspec-file-nul"],
                env=isolated_env, input_bytes=b"\0".join(force_paths) + b"\0",
            )
        diff_args = [*args, "diff", "--cached", "--no-ext-diff", "--no-textconv", "--no-renames"]
        patch = _run(root, [*diff_args, "--binary", "--full-index", resolved_base, "--"], env=isolated_env)
        paths = _run(root, [*diff_args, "--name-only", "-z", resolved_base, "--"], env=isolated_env)
        changed_paths = tuple(os.fsdecode(path) for path in paths.split(b"\0") if path)
        tree_id = _run(root, [*args, "write-tree"], env=isolated_env).decode("ascii").strip()
    if bool(patch) != bool(changed_paths):
        raise SubmissionError("Git patch and changed-path inspection disagree")
    return GitSubmission(resolved_base, patch, changed_paths, tree_id)


def _reject_escaping_links(candidate: Path) -> None:
    root = candidate.resolve()
    for item in root.rglob("*"):
        if ".git" in item.relative_to(root).parts or not item.is_symlink():
            continue
        # Even an absolute link currently pointing inside this candidate would
        # point outside the newly materialized deliverable. Relative internal
        # links retain their meaning when the whole tree is relocated.
        link = Path(os.readlink(item))
        if link.is_absolute() or not item.resolve(strict=False).is_relative_to(root):
            raise SubmissionError(
                "Candidate contains a non-relocatable or escaping symlink: "
                + item.relative_to(root).as_posix()
            )


def materialize_git_submission(
    candidate: Path,
    base_commit: str,
    target: Path,
    *,
    excluded_paths: tuple[str, ...] = (),
) -> GitSubmission:
    """Rebuild exactly the exported Git artifact in a new, clean directory.

    The target must not exist and is never overwritten or deleted. A failed
    rebuild leaves an incomplete directory for diagnosis, not a deliverable.
    Only base-commit files plus the patch enter this tree: ignored runtime data,
    untracked scratch excluded by the caller, and verification outputs cannot
    silently make a check pass. No checkout hooks or network fetch are used.
    The resulting repository has HEAD at the original base and the delivered
    changes staged, so the ordinary runner can export the same patch again.
    """
    candidate = Path(candidate).resolve()
    destination = Path(target).absolute()
    if os.path.lexists(destination):
        raise SubmissionError(f"Delivery target already exists: {destination}")
    if not destination.parent.is_dir() or destination.parent.resolve() != destination.parent:
        raise SubmissionError("Delivery target parent must be an existing non-redirected directory")
    if destination.is_relative_to(candidate):
        raise SubmissionError("Delivery target must be outside the candidate workspace")
    _reject_escaping_links(candidate)
    submission = inspect_git_submission(candidate, base_commit, excluded_paths=excluded_paths)
    repo = _repository(candidate)
    assert repo is not None
    root, args, env = repo
    git_dir = _run(root, [*args, "rev-parse", "--absolute-git-dir"], env=env)
    source_git = Path(os.fsdecode(git_dir.rstrip(b"\r\n"))).resolve()
    destination.mkdir()
    _run(destination, ["init", "--quiet"], env=env)
    # The explicit local Git directory is the sole source. Fetch copies objects
    # instead of leaving an alternate-object dependency on a disposable snapshot.
    _run(destination, ["-c", "protocol.file.allow=always", "fetch", "--quiet", "--no-tags",
                       "--no-write-fetch-head", str(source_git), submission.base_commit], env=env)
    _run(destination, ["config", "core.autocrlf", "false"], env=env)
    _run(destination, ["config", "core.hooksPath", str(destination / ".git" / "disabled-hooks")], env=env)
    _run(destination, ["read-tree", "--reset", "-u", submission.base_commit], env=env)
    _run(destination, ["update-ref", "HEAD", submission.base_commit], env=env)
    if submission.patch:
        _run(destination, ["apply", "--index", "--binary", "--whitespace=nowarn", "-"],
             env=env, input_bytes=submission.patch)
    actual_tree = _run(destination, ["write-tree"], env=env).decode("ascii").strip()
    if actual_tree != submission.tree_id:
        raise SubmissionError("Clean patch application did not reproduce the selected Git tree")
    rebuilt = inspect_git_submission(destination, submission.base_commit)
    if rebuilt.tree_id != submission.tree_id or rebuilt.patch != submission.patch:
        raise SubmissionError("Materialized working files differ from the exported artifact")
    _reject_escaping_links(destination)
    return submission


def export_git_submission(
    candidate: Path,
    base_commit: str,
    output_path: Path,
    *,
    excluded_paths: tuple[str, ...] = (),
) -> GitSubmission:
    """Inspect first, then preserve the patch bytes in an external artifact."""
    target = Path(output_path).resolve()
    if target.is_relative_to(Path(candidate).resolve()):
        raise SubmissionError("Patch output must be outside the candidate workspace")
    submission = inspect_git_submission(candidate, base_commit, excluded_paths=excluded_paths)
    target.write_bytes(submission.patch)
    return submission
