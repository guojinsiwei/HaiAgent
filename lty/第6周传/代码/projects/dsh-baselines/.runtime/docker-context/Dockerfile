FROM longcli-audit/make-pytest:2015f37
COPY node-v24.9.0-linux-x64.tar.xz /tmp/node.tar.xz
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
