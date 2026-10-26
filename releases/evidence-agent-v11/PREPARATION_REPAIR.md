# 2026-09-18：固定 100 题中 15 题准备失败的修复

原题单不修改。旧批次 `/mnt/lizh639/bestfgs-runs/swe100-v1` 的 `batch.json` 保持字节不变，修复过程另记 `repairs/prepfix-v2-*/repair.json`。已成功 85 题的状态、ready 清单和依赖清单做前后哈希校验；不重装它们。

修复版项目部署到新目录 `BestFGS-compare-v2`，不要覆盖旧项目或使用旧运行器启动后续搜索。两组对照都应使用 v2：准备验证和实际命令执行均支持 `src/`、`lib/`、仓库根目录源码布局。

仅在失败题的新环境应用显式构建版本覆盖；原始 recipe、base commit、题目内容不变，覆盖版本写入各题 ready 清单，实际环境另外保存 pip freeze：

- Matplotlib 3.4/3.6：修复 lib 导入优先级；使用 setuptools-scm 7.1.0，NumPy 分别为 1.24.4/1.25.2（准备清单中的 pip 版本），构建工具固定版本。
- scikit-learn 1.3 的三个历史提交：NumPy 1.26.4（缓存清单 pip 层版本）、Cython 0.29.36（满足代码声明的 >=0.29.33，避开当前历史代码的 Cython 3 编译失败）。
- xarray 0.12：显式安装 setuptools-scm 7.1.0，避免旧 setup_requires 临时拉入拆分依赖的新版本；NumPy 1.23.0。
- Astropy 4.3/5.1：补 extension-helpers 0.1、setuptools-scm 7.1.0；分别使用其 pyproject 指定的 Cython 0.29.22/0.29.30，NumPy 1.25.2。
- Pylint 3.0：setuptools 68.0.0 提供 editable 构建接口。
- Sphinx 7.2：不改变依赖，重试下载。

这是记录在案的 Notebook 构建适配，不宣称依赖与官方 Docker 镜像逐字相同；Agent 与 baseline 必须使用修复后同一份逐题环境，最终仍用同一个官方 harness 评测。

```bash
cd /mnt/lizh639/BestFGS-compare-v2
/mnt/lizh639/envs/bestfgs/bin/python repair_swe_preparation.py \
  --root /mnt/lizh639/bestfgs-runs/swe100-v1 --expected-failures 15
```

下载有限重试；不改系统 DNS，不关闭工作区导入隔离检查，不读参考补丁/官方测试，不调用模型 API。构建任务在独立 tmux 会话运行。准备成功不等于解题成功，仍需检查最后的状态汇总。

原理参考：[scikit-learn 构建兼容性说明](https://github.com/scikit-learn/scikit-learn/issues/26858)、[Astropy extension-helpers 构建依赖说明](https://extension-helpers.readthedocs.io/en/latest/using.html)。具体版本首先以该任务 checkout 的构建声明与已冻结环境清单为依据。
