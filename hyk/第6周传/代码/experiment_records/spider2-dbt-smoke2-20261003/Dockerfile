FROM longcli-paired10-20261001/make-pytest:2015f37
RUN python3 -m venv --without-pip /opt/spider \
 && /root/.local/bin/uv pip install --python /opt/spider/bin/python --no-cache --index-url https://pypi.org/simple duckdb==1.2.2 pandas==2.2.3 numpy==2.2.6 dbt-duckdb==1.9.6 PyYAML==6.0.2
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 DBT_SEND_ANONYMOUS_USAGE_STATS=false DBT_PROFILES_DIR=.
ENV PATH=/opt/spider/bin:/usr/local/bin:/usr/bin:/bin
CMD ["bash"]
