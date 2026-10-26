"""Reclassify receipts and merge an attested official regrade; retain originals."""
import datetime,hashlib,json
from pathlib import Path
import campaign
from queue_policy import finish,summary
from storage import atomic_json,supervisor_lock
R=Path(__file__).resolve().parent

def main():
    with supervisor_lock(R):
        h=campaign.read(R/'health.json')
        if h['state']!='finished' or h.get('active'):raise RuntimeError('Campaign must be stopped')
        backup=R/'repair-v1/original/health.json'
        if not backup.exists():raise RuntimeError('Original state archive required')
        recovery=campaign.read(R/'repair-v1/regrade.json')
        changes=[]
        for row in h['rows']:
            old=row['state'];result=campaign.trial(row)
            if recovery.get('source')==result.get('trial') and recovery.get('verifier_result') and not recovery.get('exception_type'):
                target=Path(recovery['trial']);graded=campaign.read(target/'result.json')
                lifecycle=campaign.read(target/'lifecycle.json')
                stages=[x.get('stage') for x in lifecycle.get('events',[])]
                if graded.get('exception_info') or lifecycle.get('failures') or not all(x in stages for x in ['artifacts_collected','verifying','verifier_finished','cleanup_succeeded']):raise RuntimeError('Incomplete regrade receipt')
                src=Path(result['trial'])/'artifacts'
                for name,digest in recovery['artifacts_sha256'].items():
                    if hashlib.sha256((src/name).read_bytes()).hexdigest()!=digest:raise RuntimeError('Source artifact drift')
                report=campaign.read(target/'verifier/ctrf.json').get('results',{}).get('summary',{})
                reward=graded['verifier_result']['rewards']['reward']
                if not report.get('tests') or (reward==1 and report.get('passed')!=report['tests']):raise RuntimeError('Invalid official test report')
                if not result.get('budget_exhausted'):raise RuntimeError('Unexpected solver termination needs separate review')
                result.update(reward=reward,engineering_clean=True,score_recovery=str(target),completion='budget_exhausted',
                    original_exception_type=result['exception_type'],exception_type=None,lifecycle_status='recovered_by_official_regrade',collection_failures=[])
            finish(row,result)
            changes.append(dict(job=row['job'],before=old,after=row['state'],reward=result.get('reward')))
        h.update(summary=summary(h['rows']),repaired_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
        atomic_json(R/'repair-v1/reclassification.json',dict(changes=changes,paid_calls=0))
        atomic_json(R/'health.json',h);atomic_json(R/'admissions.json',h)
        print(json.dumps(h['summary'],indent=2))
if __name__=='__main__':main()
