"""Explicit read-only inspection/reconciliation and drain requests; no model launch."""
import argparse
import json
from pathlib import Path
from receipts import read_receipt
from recovery import reconcile
from storage import atomic_json, supervisor_lock


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['inspect','reconcile','drain'])
    args=parser.parse_args();root=Path(__file__).resolve().parent
    state,status=read_receipt(root/'admissions.json')
    if status!='present':raise RuntimeError('No valid campaign checkpoint: '+status)
    if args.action=='inspect':
        print(json.dumps(state,indent=2));return
    if args.action=='drain':
        atomic_json(root/'control.json',dict(command='drain',supervisor_identity=state.get('supervisor_identity')))
        print('Drain requested. Active trial will finish; new dispatches will pause.');return
    from campaign import trial
    with supervisor_lock(root):
        restored,problems=reconcile(root,state,trial)
        # A report is reviewable; it is not authorization to dispatch a trial.
        atomic_json(root/'reconciliation.json',dict(resumable=not problems,problems=problems,state=restored))
        print(json.dumps(dict(resumable=not problems,problems=problems),indent=2))


if __name__=='__main__':main()
