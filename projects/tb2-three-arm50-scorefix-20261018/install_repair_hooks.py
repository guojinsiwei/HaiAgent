from pathlib import Path
R=Path(__file__).resolve().parent
p=R/'agents.py';s=p.read_text()
assert 'class ReplayDSH' not in s
s+='''
class ReplayDSH(OfflinePureDSH):
    @staticmethod
    def name():return 'dsh-original-submission-score-only'
    async def run(self,instruction,environment,context):
        import hashlib
        source=ROOT/'recovered-submission/pipeline_parallel.py'
        evidence=json.loads((source.parent/'provenance.json').read_text())
        assert hashlib.sha256(source.read_bytes()).hexdigest()==evidence['file_sha256']
        await environment.upload_file(source,'/app/pipeline_parallel.py')
        check=await self.exec_as_root(environment,'sha256sum /app/pipeline_parallel.py',timeout_sec=30)
        assert check.return_code==0 and check.stdout.split()[0]==evidence['file_sha256']
        context.metadata=dict(paid_calls=0,score_only=True,original_trial=evidence['original_trial'],submission_sha256=evidence['file_sha256'])
''';p.write_text(s)
p=R/'lifecycle_guard.py';s=p.read_text();needle="            record(self,'artifacts_collected')"
assert s.count(needle)==1
s=s.replace(needle,"""            # Snapshot before verifier dependencies/tests can touch submitted files.
            from submission_snapshot import snapshot
            await snapshot(self)
"""+needle);p.write_text(s)
p=R/'upload_verified.py';s=p.read_text();s=s.replace("digest=hashlib.sha256(source.read_bytes()).hexdigest()","with source.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()");p.write_text(s)
print('HOOKS_INSTALLED')
