"""Package an explicit allowlist; never include test sessions or audit directories."""
import subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def build():
    files=['node','kz/node_modules','kz/src','kz/scripts','kz/tests','kz/config','kz/package.json','kz/package-lock.json']
    files+=['kz/'+n for n in ('shared-budget.mjs','route.patch.yml','route-audit.mjs','boot-guard.mjs','container-run.mjs','deadline.mjs','.runtime/kz.patch.yml','.runtime/transport.patch.yml')]
    files += ['kz/'+n for n in ('provider-guard.mjs','spending-client.mjs','messages-protocol.mjs')]
    temporary=ROOT/'runtime-next.tar.gz'
    subprocess.run(['tar','-czf',str(temporary),'-C',str(ROOT/'runtime'),*files],check=True)
    temporary.replace(ROOT/'runtime-final.tar.gz')
if __name__=='__main__':build()
