from host_agent import PairAgent
class HLD(PairAgent):
 arm='hld'
 @staticmethod
 def name():return 'hld-v5-tb4'
class Recuris(PairAgent):
 arm='recuris'
 @staticmethod
 def name():return 'recuris-v5-tb4'
class OfflineHLD(HLD):
 @staticmethod
 def name():return 'hld-v5-keyless'
 async def run(self,instruction,environment,context):
  result=await self.exec_as_agent(environment,'/opt/node/bin/node --check /opt/kz/container-run.mjs && /opt/kz-python/bin/python3 --version',cwd=self.cwd,timeout_sec=30)
  if result.return_code:raise RuntimeError('Runtime entry failed')
  import os
  if os.environ.get('ENTRY_ACCEPTANCE')=='1':
   from entry_probe import probe
   await probe(self,environment,instruction)
  context.metadata={'paid_calls':0,'offline_acceptance':True}
class OfflineRecuris(OfflineHLD):
 arm='recuris'
 @staticmethod
 def name():return 'recuris-v5-keyless'
