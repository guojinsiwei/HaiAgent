from __future__ import annotations

import hashlib
import locale
import logging
import os
import re
import shutil
import stat
import subprocess
import sys
import time
import tokenize
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Protocol
from .experiment_metrics import ExperimentRecorder, measured_batch, measured_command

from .models import (
    CommandResult,
    CommandSpec,
    EnvironmentSnapshot,
    ExecutionOutcome,
    MacroAction,
    new_id,
)

'''
提供可被 BestFGS 调用的真实 CLI 环境。每个动作都从父快照复制出隔离工作区，在其中按预算执行命令，记录返回码、输出、耗时和文件变化，
并支持恢复分支与最终复验。它还负责路径边界检查、输出编码兼容和工作区修改检测，使不同搜索分支不会互相覆盖。
'''
logger = logging.getLogger(__name__)


#CLI环境接口：搜索算法只依赖这三个方法，不关心底层是真实目录还是测试环境
class CLIEnvironment(Protocol):
    #建立任务开始时的根环境快照
    def initial_snapshot(self) -> EnvironmentSnapshot:
        ...

    #从指定父快照执行一个宏动作，并返回执行结果和新的子快照
    def execute(
        self,
        snapshot: EnvironmentSnapshot,
        action: MacroAction,
        max_commands: int,
    ) -> ExecutionOutcome:
        ...

    # 根据快照 ID 恢复可执行环境，用于切换到不同搜索分支。
    def restore(self, snapshot: EnvironmentSnapshot) -> EnvironmentSnapshot:
        ...

    #在临时副本中重放候选解的功能验证，不改变已保存快照
    def verify(
        self,
        snapshot: EnvironmentSnapshot,
        commands: tuple[CommandSpec, ...],
    ) -> tuple[CommandResult, ...]:
        ...


#环境安全配置：命令超时、输出截断长度、默认禁止调用的危险程序
@dataclass(slots=True)
class EnvironmentConfig:
    command_timeout_seconds: int = 60
    max_output_chars: int = 12_000
    deny_executables: list[str] = field(
        default_factory=lambda: [
            "rm",
            "rmdir",
            "del",
            "erase",
            "format",
            "shutdown",
            "reboot",
        ]
    )

#判断path是否位于parent目录内部，主要用于阻止cwd越出隔离工作区
def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False

#遍历工作区文件内容生成环境指纹，用于判断两个环境状态是否相同
def _tree_fingerprint(root: Path) -> str:
    return _manifest_fingerprint(_tree_manifest(root))


def _tree_manifest(root: Path) -> dict[str, tuple[int, str]]:
    """Build the compact file state used for fingerprints and change paths."""

    manifest: dict[str, tuple[int, str]] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if any(part in {".git", "__pycache__", ".bestfgs_runs"} for part in relative.parts):
            continue
        manifest[relative.as_posix()] = (path.stat().st_size, _file_digest(path))
    return manifest


def _manifest_fingerprint(manifest: dict[str, tuple[int, str]]) -> str:
    digest = hashlib.sha256()
    for relative, (size, file_digest) in sorted(manifest.items()):
        digest.update(relative.encode("utf-8"))
        digest.update(str(size).encode("ascii"))
        digest.update(file_digest.encode("ascii"))
    return digest.hexdigest()


def _changed_manifest_paths(
    parent: dict[str, tuple[int, str]],
    child: dict[str, tuple[int, str]],
) -> tuple[str, ...]:
    return tuple(
        path
        for path in sorted(set(parent).union(child))
        if parent.get(path) != child.get(path)
    )


#子进程输出先按字节捕获，再依次尝试UTF-8与Windows本地编码，避免reader线程解码崩溃
def _decode_process_output(data: bytes | str | None) -> str:
    if data is None:
        return ""
    if isinstance(data, str):
        return data
    encodings = ("utf-8", locale.getpreferredencoding(False), "gb18030")
    tried: set[str] = set()
    for encoding in encodings:
        normalized = encoding.casefold()
        if normalized in tried:
            continue
        tried.add(normalized)
        try:
            return data.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return data.decode("utf-8", errors="replace")

# 复制父工作区形成新分支，并排除缓存和 BestFGS 自身生成的运行目录。
def _copy_workspace(source: Path, target: Path) -> None:
    def ignore(_: str, names: list[str]) -> set[str]:
        blocked = {"__pycache__", ".bestfgs_runs"}
        return {name for name in names if name in blocked}

    #保留符号链接，避免快照把仓库中的链接展开成普通文件并污染最终git diff。
    shutil.copytree(source, target, ignore=ignore, symlinks=True)


def _remove_verification_workspace(verification_dir: Path, run_root: Path) -> None:
    """Remove only this disposable child; Git's Windows read-only objects may need a retry."""
    boundary = run_root.resolve(strict=True)
    if run_root.absolute() != boundary:
        raise ValueError(f"Verification run root was redirected: {run_root}")
    target = verification_dir.absolute()
    if target.parent.resolve(strict=True) != boundary or not target.name.startswith("final_verification_"):
        raise ValueError(f"Verification cleanup is outside its temporary subtree: {target}")
    if not os.path.lexists(target):
        return
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    if target.is_symlink() or getattr(target.lstat(), "st_file_attributes", 0) & reparse_flag:
        raise ValueError(f"Verification cleanup root must not be a link: {target}")
    resolved = target.resolve(strict=True)
    if resolved == boundary or resolved.parent != boundary or not resolved.is_dir():
        raise ValueError(f"Invalid verification cleanup subtree: {resolved}")

    def retry_readonly(function, failed_path, exc_info):
        error = exc_info[1]
        # A locked file, an ACL failure, or any other I/O problem must still be
        # reported.  Only retry Windows read-only deletion, never traversal.
        if (sys.platform != "win32" or not isinstance(error, PermissionError)
                or function not in (os.unlink, os.remove, os.rmdir)):
            raise error.with_traceback(exc_info[2])
        failed = Path(failed_path).absolute()
        actual = failed.resolve(strict=True)
        if (resolved.resolve(strict=True) != resolved
                or not _is_relative_to(actual, resolved)
                or actual == boundary):
            raise ValueError(f"Refusing permission changes outside verification subtree: {failed}") from error
        # Reject symlinks and junctions at every level before chmod can follow
        # them.  Neither the source repository nor a linked external target is
        # ever made writable to clean this copy.
        current = failed
        while True:
            info = current.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & reparse_flag:
                raise ValueError(f"Refusing permission changes through a link: {current}") from error
            if current == resolved:
                break
            if not _is_relative_to(current, resolved):
                raise ValueError(f"Refusing permission changes outside verification subtree: {failed}") from error
            current = current.parent
        info = failed.lstat()
        if stat.S_ISREG(info.st_mode) and info.st_nlink > 1:
            raise ValueError(f"Refusing permission changes on a multiply linked file: {failed}") from error
        readonly = getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_READONLY", 0x1)
        if not readonly and info.st_mode & stat.S_IWRITE:
            raise error.with_traceback(exc_info[2])
        os.chmod(failed, info.st_mode | stat.S_IWRITE)
        function(failed_path)

    # onerror is available throughout the supported Python 3.11+ range.
    shutil.rmtree(resolved, onerror=retry_readonly)


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _changed_files(parent: Path, child: Path) -> tuple[Path, ...]:
    """返回新增或内容变化的文件；删除文件无需做语法检查。"""
    changed: list[Path] = []
    for child_path in sorted(child.rglob("*")):
        if not child_path.is_file() or child_path.is_symlink():
            continue
        relative = child_path.relative_to(child)
        if any(part in {"__pycache__", ".bestfgs_runs", ".git"} for part in relative.parts):
            continue
        parent_path = parent / relative
        if (
            not parent_path.is_file()
            or parent_path.is_symlink()
            or parent_path.stat().st_size != child_path.stat().st_size
            or _file_digest(parent_path) != _file_digest(child_path)
        ):
            changed.append(relative)
    return tuple(changed)


def _validate_workspace_change(parent: Path, child: Path) -> tuple[CommandResult, ...]:
    """自动阻止语法损坏和未解决的合并冲突进入候选解。"""
    started = time.monotonic()
    changed = _changed_files(parent, child)
    python_files = tuple(path for path in changed if path.suffix.casefold() == ".py")
    errors: list[str] = []
    for relative in python_files:
        path = child / relative
        try:
            with tokenize.open(path) as stream:
                source = stream.read()
            compile(source, str(relative), "exec", dont_inherit=True)
        except (OSError, SyntaxError, UnicodeError) as error:
            errors.append(
                f"{relative.as_posix()}: {type(error).__name__}: {error}"
            )

    conflict_pattern = re.compile(r"^(<<<<<<<|=======|>>>>>>>)", re.MULTILINE)
    for relative in changed:
        path = child / relative
        if path.stat().st_size > 2 * 1024 * 1024:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if conflict_pattern.search(text):
            errors.append(f"{relative.as_posix()}: contains unresolved merge markers")

    command = CommandSpec(
        argv=("internal-validation-gate",),
        description="自动验证修改文件的Python语法与合并冲突标记",
    )
    checked = (
        f"checked {len(changed)} changed files; "
        f"compiled {len(python_files)} Python files"
    )
    return (
        CommandResult(
            command=command,
            return_code=1 if errors else 0,
            stdout=checked if not errors else "",
            stderr="\n".join(errors),
            duration_seconds=time.monotonic() - started,
        ),
    )

#真实CLI环境：每条搜索边都在父快照的独立副本中执行，避免不同分支互相污染
@dataclass(slots=True)
class ForkedWorkspaceEnvironment:
    """Executes each search action in an isolated copy of its parent snapshot."""

    seed_workspace: Path
    run_root: Path
    config: EnvironmentConfig = field(default_factory=EnvironmentConfig)
    allowed_executables: set[str] | None = None
    recorder: ExperimentRecorder | None = None
    _snapshots: dict[str, EnvironmentSnapshot] = field(default_factory=dict, init=False)
    _snapshot_manifests: dict[str, dict[str, tuple[int, str]]] = field(
        default_factory=dict,
        init=False,
    )
    _root_manifest: dict[str, tuple[int, str]] | None = field(default=None, init=False)

    #dataclass初始化后的安全检查：种子目录必须存在，运行目录不能位于种子目录内部
    def __post_init__(self) -> None:
        self.seed_workspace = self.seed_workspace.resolve()
        self.run_root = self.run_root.resolve()
        if not self.seed_workspace.is_dir():
            raise ValueError(f"seed_workspace is not a directory: {self.seed_workspace}")
        if self.run_root == self.seed_workspace or _is_relative_to(self.run_root, self.seed_workspace):
            raise ValueError("run_root must be outside seed_workspace")
        self.run_root.mkdir(parents=True, exist_ok=True)

    #复制种子工作区并创建根快照；同一run_root不允许重复初始化
    def initial_snapshot(self) -> EnvironmentSnapshot:
        target = self.run_root / "root"
        if target.exists():
            raise FileExistsError(f"run root already initialized: {target}")
        logger.info("[环境] 正在复制种子工作区到隔离根快照")
        _copy_workspace(self.seed_workspace, target)
        snapshot = self._make_snapshot(target, "initial isolated workspace")
        self._snapshots[snapshot.snapshot_id] = snapshot
        logger.info("[环境] 已创建初始隔离工作区：%s", target)
        return snapshot

    #只允许恢复本环境已经登记、并且路径仍位于run_root下的快照
    def restore(self, snapshot: EnvironmentSnapshot) -> EnvironmentSnapshot:
        known = self._snapshots.get(snapshot.snapshot_id)
        if known is None:
            raise KeyError(f"unknown snapshot: {snapshot.snapshot_id}")
        location = Path(known.location).resolve()
        if not _is_relative_to(location, self.run_root) or not location.is_dir():
            raise ValueError(f"invalid snapshot location: {location}")
        return known

    #先复制父快照，再顺序执行宏动作中的cmd；任意命令失败后停止后续命令
    @measured_batch("action")
    def execute(
        self,
        snapshot: EnvironmentSnapshot,
        action: MacroAction,
        max_commands: int,
    ) -> ExecutionOutcome:
        parent = self.restore(snapshot)
        child_dir = self.run_root / new_id("snapshot")
        logger.info("[环境] 正在复制父快照，为动作创建隔离分支")
        _copy_workspace(Path(parent.location), child_dir)
        logger.info("[环境] 已为动作创建新快照：%s", child_dir.name)
        results: list[CommandResult] = []
        selected_commands = action.commands[:max_commands]
        for index, command in enumerate(selected_commands, start=1):
            executable = Path(command.argv[0]).name if command.argv else "<empty>"
            logger.info(
                "[环境] 执行命令 %d/%d：%s（%s）",
                index,
                len(selected_commands),
                command.description,
                executable,
            )
            result = self._execute_command(child_dir, command)
            results.append(result)
            logger.info(
                "[环境] 命令结束：return_code=%d，耗时=%.2f秒，成功=%s",
                result.return_code,
                result.duration_seconds,
                result.succeeded,
            )
            if not result.succeeded:
                break
        intermediate = self._make_snapshot(
            child_dir,
            f"after semantic action {action.name!r}; direction={action.semantic_direction_id}",
        )
        validation_results: tuple[CommandResult, ...] = ()
        if parent.fingerprint != intermediate.fingerprint:
            validation_results = _validate_workspace_change(
                Path(parent.location),
                child_dir,
            )
            validation = validation_results[0]
            logger.info(
                "[验证] 修改后自动门槛：成功=%s；%s%s",
                validation.succeeded,
                validation.stdout,
                f"；{validation.stderr}" if validation.stderr else "",
            )
        functional_results: list[CommandResult] = []
        remaining_commands = max(0, max_commands - len(results))
        if (
            results
            and all(result.succeeded for result in results)
            and all(result.succeeded for result in validation_results)
            and remaining_commands > 0
        ):
            selected_verification = action.verification_commands[:remaining_commands]
            self._snapshots[intermediate.snapshot_id] = intermediate
            # Tests may create binaries or reports; none may enter the submission.
            functional_results.extend(self.verify(intermediate, selected_verification))
        resulting = self._make_snapshot(
            child_dir,
            f"after semantic action {action.name!r}; direction={action.semantic_direction_id}",
        )
        parent_manifest = self._snapshot_manifests[parent.snapshot_id]
        resulting_manifest = self._snapshot_manifests[resulting.snapshot_id]
        resulting = replace(
            resulting,
            metadata={
                **resulting.metadata,
                "changed_paths_from_parent": _changed_manifest_paths(
                    parent_manifest,
                    resulting_manifest,
                ),
            },
        )
        self._snapshots[resulting.snapshot_id] = resulting
        return ExecutionOutcome(
            parent_snapshot=parent,
            resulting_snapshot=resulting,
            action=action,
            command_results=tuple(results),
            validation_results=validation_results,
            functional_validation_results=tuple(functional_results),
        )

    @measured_batch("verification")
    def verify(
        self,
        snapshot: EnvironmentSnapshot,
        commands: tuple[CommandSpec, ...],
    ) -> tuple[CommandResult, ...]:
        """在一次性副本中重放功能验证，避免验证命令污染候选快照。"""

        parent = self.restore(snapshot)
        verification_dir = self.run_root / new_id("final_verification")
        _copy_workspace(Path(parent.location), verification_dir)
        baseline = _tree_manifest(verification_dir)
        results: list[CommandResult] = []
        logger.info("[最终验证] 正在复验候选快照：%s", parent.snapshot_id)
        try:
            for index, command in enumerate(commands, start=1):
                logger.info(
                    "[最终验证] 执行 %d/%d：%s",
                    index,
                    len(commands),
                    command.description,
                )
                result = self._execute_command(verification_dir, command)
                current = _tree_manifest(verification_dir)
                test_caches = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
                modified = sorted(path for path, value in baseline.items()
                                  if current.get(path) != value
                                  and not test_caches.intersection(Path(path).parts)
                                  and not Path(path).name.startswith(".coverage"))
                if modified:
                    result = replace(
                        result, return_code=1,
                        stderr=result.stderr + "\nVerification modified candidate files: "
                        + ", ".join(modified[:12]),
                    )
                results.append(result)
                if not result.succeeded:
                    break
            return tuple(results)
        finally:
            _remove_verification_workspace(verification_dir, self.run_root)

    #执行单条底层cmd，同时处理禁止程序、允许列表、cwd越界、超时和输出截断
    @measured_command
    def _execute_command(self, snapshot_dir: Path, command) -> CommandResult:
        started = time.monotonic()
        if not command.argv:
            return CommandResult(command, 126, "", "empty argv", 0.0, blocked=True)
        #只比较可执行文件名，并忽略Windows下.exe后缀和大小写差异
        executable = Path(command.argv[0]).name.casefold().removesuffix(".exe")
        denied = {item.casefold().removesuffix(".exe") for item in self.config.deny_executables}
        if executable in denied:
            return CommandResult(
                command,
                126,
                "",
                f"blocked executable: {command.argv[0]}",
                time.monotonic() - started,
                blocked=True,
            )
        if self.allowed_executables is not None:
            allowed = {item.casefold().removesuffix(".exe") for item in self.allowed_executables}
            if executable not in allowed:
                return CommandResult(
                    command,
                    126,
                    "",
                    f"executable is not allow-listed: {command.argv[0]}",
                    time.monotonic() - started,
                    blocked=True,
                )
        # 基准任务经常在题面中把工作区写成 /app 或 /testbed。seed_workspace
        # 已经被复制为当前搜索分支，因此这些原工作区路径必须映射到本分支，
        # 不能直接访问种子目录，否则会绕过快照隔离并污染其他搜索分支。
        mapped_cwd = self._rewrite_workspace_references(command.cwd, snapshot_dir)
        cwd_path = Path(mapped_cwd)
        cwd = (
            cwd_path.resolve()
            if cwd_path.is_absolute()
            else (snapshot_dir / cwd_path).resolve()
        )
        if not _is_relative_to(cwd, snapshot_dir.resolve()) or not cwd.is_dir():
            return CommandResult(
                command,
                126,
                "",
                f"cwd escapes snapshot or is missing: {command.cwd}",
                time.monotonic() - started,
                blocked=True,
            )
        timeout = command.timeout_seconds or self.config.command_timeout_seconds
        runtime_argv = [
            self._rewrite_workspace_references(part, snapshot_dir)
            for part in command.argv
        ]
        runtime_stdin = (
            self._rewrite_workspace_references(command.stdin, snapshot_dir)
            if command.stdin is not None
            else None
        )
        runtime_env = os.environ.copy()
        runtime_env["RETRAC_WORKSPACE"] = str(snapshot_dir.resolve())
        if runtime_env.get("BESTFGS_TASK_SOURCE_PATH") == "1":
            # Batch environments can contain editable installs pointing at the seed.
            # Task Python must import the current branch (including src layouts).
            runtime_env["PYTHONPATH"] = os.pathsep.join([
                str(snapshot_dir.resolve() / "src"), str(snapshot_dir.resolve() / "lib"), str(snapshot_dir.resolve()),
                runtime_env.get("PYTHONPATH", ""),
            ])
        try:
            #shell=False表示argv直接传给程序，不经过Shell再次解析
            completed = subprocess.run(
                runtime_argv,
                cwd=cwd,
                input=runtime_stdin.encode("utf-8") if runtime_stdin is not None else None,
                capture_output=True,
                timeout=timeout,
                env=runtime_env,
                shell=False,
                check=False,
            )
            return CommandResult(
                command,
                completed.returncode,
                _decode_process_output(completed.stdout)[-self.config.max_output_chars :],
                _decode_process_output(completed.stderr)[-self.config.max_output_chars :],
                time.monotonic() - started,
            )
        except subprocess.TimeoutExpired as error:
            stdout = _decode_process_output(error.stdout)
            stderr = _decode_process_output(error.stderr)
            return CommandResult(
                command,
                124,
                stdout[-self.config.max_output_chars :],
                stderr[-self.config.max_output_chars :],
                time.monotonic() - started,
                timed_out=True,
            )
        except OSError as error:
            return CommandResult(
                command,
                127,
                "",
                str(error),
                time.monotonic() - started,
            )

    #把种子工作区的绝对路径及嵌入命令参数中的路径统一改写为当前分支路径
    def _rewrite_workspace_references(self, text: str, snapshot_dir: Path) -> str:
        rewritten = text
        #POSIX形式在Linux原样可用，在Windows也能被Path和大多数CLI识别；同时
        #避免把C:\\...直接插入python -c字符串后触发\\U转义语法错误。
        target = snapshot_dir.resolve().as_posix()
        aliases = sorted(
            {str(self.seed_workspace), self.seed_workspace.as_posix()},
            key=len,
            reverse=True,
        )
        for alias in aliases:
            if not alias:
                continue
            #只替换完整路径前缀；避免把 /app 意外替换进 /application。
            boundary = r"(?=$|[\\/\"'\s\),;:\]])"
            rewritten = re.sub(
                re.escape(alias) + boundary,
                lambda _match: target,
                rewritten,
            )
        return rewritten

    #根据目录位置、文件指纹和文件数量整理一个新的环境快照对象
    def _make_snapshot(self, location: Path, summary: str) -> EnvironmentSnapshot:
        snapshot_id = new_id("snapshot")
        manifest = _tree_manifest(location)
        if self._root_manifest is None:
            self._root_manifest = dict(manifest)
        snapshot = EnvironmentSnapshot(
            snapshot_id=snapshot_id,
            location=str(location),
            fingerprint=_manifest_fingerprint(manifest),
            summary=summary,
            metadata={
                "file_count": len(manifest),
                "changed_paths_from_root": _changed_manifest_paths(
                    self._root_manifest,
                    manifest,
                ),
            },
        )
        self._snapshot_manifests[snapshot_id] = manifest
        return snapshot
