// Fallback for Docker Hub outages: locally cached image + verified official Node tarball.
import {readFile,writeFile,readdir} from 'node:fs/promises';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('../',import.meta.url)),dir=path.join(root,'.runtime/docker-context');
const report=JSON.parse((await readFile(path.join(root,'audit/container-isolation.json'),'utf8')).replace(/^\uFEFF/,''));
const file='node-v24.9.0-linux-x64.tar.xz';
const hash=b=>createHash('sha256').update(b).digest('hex');
const actual=hash(await readFile(path.join(dir,file)));
const expected=(await readFile(path.join(dir,'SHASUMS256.txt'),'utf8')).split('\n').find(l=>l.endsWith('  '+file))?.split(' ')[0];
if(!expected||actual!==expected)throw new Error('Official Node SHA256 mismatch');
const wheels={};for(const f of await readdir(path.join(dir,'wheels')))wheels[f]=hash(await readFile(path.join(dir,'wheels',f)));
await writeFile(path.join(root,'audit/linux-inputs.json'),JSON.stringify({baseImageId:report.imageId,node:{version:'24.9.0',sha256:actual,source:'https://nodejs.org/dist/v24.9.0/'},wheels},null,2));
await writeFile(path.join(dir,'python-dsh'),'#!/bin/sh\nexport PYTHONPATH=/opt/python-libs\nexec /usr/bin/python3 "$@"\n');
await writeFile(path.join(dir,'Dockerfile'),`FROM ${report.image}
COPY ${file} /tmp/node.tar.xz
RUN mkdir -p /opt/node && tar -xJf /tmp/node.tar.xz --strip-components=1 -C /opt/node && rm /tmp/node.tar.xz
ENV PATH=/opt/node/bin:$PATH
COPY wheels /opt/wheels
RUN python3 -c "import pathlib,zipfile; [zipfile.ZipFile(p).extractall('/opt/python-libs') for p in pathlib.Path('/opt/wheels').glob('*.whl')]"
COPY python-dsh /opt/python-dsh
RUN chmod +x /opt/python-dsh
COPY dsh-baselines/package.json dsh-baselines/package-lock.json /opt/baselines/dsh-baselines/
WORKDIR /opt/baselines/dsh-baselines
RUN npm ci --ignore-scripts --no-audit --no-fund
COPY dsh-baselines /opt/baselines/dsh-baselines
COPY recuris-dsh /opt/baselines/recuris-dsh
COPY taco-dsh /opt/baselines/taco-dsh
ENV BASELINE_PYTHON=/opt/python-dsh PYTHONDONTWRITEBYTECODE=1
CMD ["node","--test","tests/lifecycle.test.mjs","tests/edge.test.mjs","tests/official-wire.test.mjs"]
`);console.log('Verified cached-image Linux build context prepared.');
