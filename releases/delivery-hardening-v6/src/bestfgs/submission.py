"""Inspect the deliverable Git tree without changing a snapshot's Git state.

The base commit is captured once from the task root.  A copied snapshot's HEAD,
index metadata, and workspace fingerprint are not submission evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tempfile


class SubmissionError(RuntimeError):
    """A submission could not be inspected; callers must not assume success."""


@dataclass(frozen=True, slots=True)
class GitSubmission:
    base_commit: str
    patch: bytes
    changed_paths: tuple[str, ...]

    @property
    def has_changes(self) -> bool:
        return bool(self.patch and self.changed_paths)

    @property
    def patch_sha256(self) -> str:
        return hashlib.sha256(self.patch).hexdigest()


_EXCLUDED_COMPONENTS = frozenset({".git", "__pycache__", ".bestfgs_runs"})
_REPOSITORY_ENV = {
    "GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_PREFIX", "GIT_CEILING_DIRECTORIES",
}


def _environment() -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if key not in _REPOSITORY_ENV}
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
        result = subprocess.run(
            ["git", "-c", "core.fsmonitor=false", *args],
            cwd=root,
            env=env,
            input=input_bytes,
            capture_output=True,
            check=True,
            timeout=60,
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
    if bool(patch) != bool(changed_paths):
        raise SubmissionError("Git patch and changed-path inspection disagree")
    return GitSubmission(resolved_base, patch, changed_paths)


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
