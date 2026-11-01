"""Keyless official-grader roundtrip on an untouched starter, not a paid trial."""
import json
import secrets

from college_grader import grade
from common import ROOT, save, sha
from runner import BASE, docker


def main():
    starter = BASE / 'starter-cs61_fa24_scheme.tar.gz'
    label = 'roundtrip--fixture-' + secrets.token_hex(4) + '--cs61_fa24_scheme'
    result = grade(label, starter, sha(starter), fixture=True)
    name = result['container']
    owner = docker('inspect', name, '--format', '{{index .Config.Labels "experiment"}}').stdout.strip()
    assert owner == json.loads((ROOT / 'protocol.json').read_text())['experiment']
    assert docker('inspect', name, '--format', '{{.State.Running}}').stdout.strip() == 'false'
    docker('rm', name)
    assert result['grading_state'] == 'complete', 'Official scoring pipeline did not produce a valid report'
    acceptance = {'state': 'passed', 'fixture_job': label, 'grading_container_destroyed': True,
                  'paid_api_requests': 0, 'f2p_report_present': True, 'p2p_checks': result['p2p_count']}
    save(ROOT / 'grading-acceptance.json', acceptance)
    print(json.dumps(acceptance))


if __name__ == '__main__':
    main()
