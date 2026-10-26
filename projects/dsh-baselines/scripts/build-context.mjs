// Explicit allowlist: never send sibling projects, histories or credentials to Docker.
import {cp,mkdir,writeFile} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('../',import.meta.url)),projects=path.dirname(root);
const destination=path.join(root,'.runtime/docker-context');await mkdir(destination,{recursive:true});
for(const project of ['dsh-baselines','recuris-dsh','taco-dsh']){
  const source=path.join(projects,project),target=path.join(destination,project);await mkdir(target,{recursive:true});
  const names=project==='dsh-baselines'?['src','tests','config','package.json','package-lock.json']:['src','vendor','worker.py','package.json'];
  for(const name of names)await cp(path.join(source,name),path.join(target,name),{recursive:true});
}
const dockerfile=`FROM node:24-bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv bash ca-certificates && rm -rf /var/lib/apt/lists/*
RUN python3 -m venv /opt/venv && /opt/venv/bin/pip install --no-cache-dir pydantic==2.13.5
COPY dsh-baselines/package.json dsh-baselines/package-lock.json /opt/baselines/dsh-baselines/
WORKDIR /opt/baselines/dsh-baselines
RUN npm ci --ignore-scripts --no-audit --no-fund
COPY dsh-baselines /opt/baselines/dsh-baselines
COPY recuris-dsh /opt/baselines/recuris-dsh
COPY taco-dsh /opt/baselines/taco-dsh
ENV BASELINE_PYTHON=/opt/venv/bin/python PYTHONDONTWRITEBYTECODE=1
CMD ["node","--test","tests/lifecycle.test.mjs","tests/edge.test.mjs","tests/official-wire.test.mjs"]
`;
await writeFile(path.join(destination,'Dockerfile'),dockerfile);console.log(destination);
