"""Deterministic delivery-gap view from public task text and workspace state."""
from pathlib import PurePosixPath
import re


PATH = re.compile(
    r"(?<![\w.-])(?:/app/|\./)?(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+\."
    r"(?:json|jsonl|csv|tsv|md|txt|py|sh|yaml|yml|toml|xml|html|pdf|png|jpg|jpeg|tif|tiff|npy|npz|parquet)"
    r"(?![\w.-])", re.I)
DELIVERY_HEADING = re.compile(
    r"(?:required\s+(?:output|artifacts?|files?)|deliverables?|outputs?\s+required|"
    r"需要(?:的)?(?:输出|交付)|必需(?:输出|文件)|交付物|"
    r"^(?:generate|create|produce|生成|创建|输出)\s*:?$)", re.I)
ACTION_LINE = re.compile(
    r"(?:generate|create|produce|write|save|deliver|must\s+include|输出|生成|创建|保存|交付)", re.I)
BLOCKED_PREFIXES = ('tests/', 'solution/', 'logs/verifier/', '.git/')


def normalize_workspace_path(value):
    if not isinstance(value, str):
        raise ValueError('workspace path must be text')
    value = value.strip().replace('\\', '/')
    if value.startswith('/app/'):
        value = value[5:]
    while value.startswith('./'):
        value = value[2:]
    path = PurePosixPath(value)
    if (not value or path.is_absolute() or any(part in ('', '.', '..') for part in path.parts)
            or value.startswith(BLOCKED_PREFIXES)):
        raise ValueError('unsafe or private workspace path')
    return path.as_posix()


def _paths(text):
    result = []
    for match in PATH.finditer(text):
        try:
            value = normalize_workspace_path(match.group(0))
        except ValueError:
            continue
        if value not in result:
            result.append(value)
    return result


def requested_artifacts(task, limit=24):
    """Extract explicit public deliverables, not every path in sample commands."""
    # TaskSpec falls back to the complete goal when success_criteria is empty.
    # That fallback is useful in the UI, but unsafe for path extraction because
    # it would classify input paths in examples/commands as deliverables.
    criteria = list(task.success_criteria or ())
    selected = []
    for criterion in criteria:
        selected.extend(_paths(criterion))
    lines = task.goal.splitlines()
    in_delivery = False
    for raw in lines:
        line = raw.strip()
        heading = line.lstrip('#').strip()
        if DELIVERY_HEADING.search(heading):
            in_delivery = True
            continue
        # A new Markdown heading or a plain ``Section:`` line ends the output
        # section. This prevents input paths in Required Commands/Inputs from
        # leaking into the delivery contract.
        if in_delivery and (line.startswith('#') or
                (heading.endswith(':') and not line.startswith(('-', '*', '+')))):
            in_delivery = False
        if in_delivery or ACTION_LINE.search(line):
            selected.extend(_paths(line))
    unique = []
    for path in selected:
        if path not in unique:
            unique.append(path)
    return unique[:limit]


class DeliveryProgress:
    def __init__(self, task, environment):
        self.task, self.environment = task, environment
        self.paths = requested_artifacts(task)

    def view(self, states=None):
        states = (self.environment.dependency_state(self.paths) if self.paths else {}) if states is None else states
        artifacts = []
        missing = []
        for path in self.paths:
            state = states.get(path, 'unknown')
            exists = state not in ('missing', 'unknown')
            artifacts.append({'path': path, 'exists': exists, 'state': state})
            if not exists:
                missing.append(path)
        criteria = [{'criterion': value, 'status': 'unverified_by_controller'}
                    for value in self.task.required_success_criteria[:12]]
        if missing:
            gap = 'Explicitly requested artifact paths still missing: ' + ', '.join(missing)
        elif artifacts:
            gap = ('All extracted artifact paths exist. Their contents and task correctness remain '
                   'unverified; inspect or test them before deciding to submit.')
        else:
            gap = ('No explicit artifact path was safely extracted. Task completion remains unverified; '
                   'use the public requirements and real checks to decide what to deliver.')
        return {'criteria': criteria, 'requested_artifacts': artifacts,
                'missing_artifacts': missing, 'controller_claims_success': False,
                'delivery_gap': gap}
