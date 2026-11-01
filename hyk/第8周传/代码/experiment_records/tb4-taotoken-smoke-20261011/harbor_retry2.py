from harbor_retry1 import KZRetry1
from harbor_kz import ROOT

class KZRetry2(KZRetry1):
    async def install(self, environment):
        await super().install(environment)
        await environment.upload_file(ROOT/'route2.patch.yml','/opt/kz/route.patch.yml')
        await environment.upload_file(ROOT/'compaction-repair.patch.yml','/opt/kz/compaction-repair.patch.yml')
        await environment.upload_file(ROOT/'offline_compaction.py','/opt/kz/offline_compaction.py')
        result=await self.exec_as_root(environment,'python /opt/kz/offline_compaction.py',timeout_sec=120)
        if result.return_code:
            raise RuntimeError('Native compaction regression failed: '+(result.stdout or '')[-3000:])
