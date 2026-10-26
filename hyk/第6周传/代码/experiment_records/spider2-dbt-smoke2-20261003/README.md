# Spider2-DBT 两题适配试跑

这是工程接入和可行性试跑，不是完整官方榜单测评，也不是算法优劣对照。

- 题目：asset001（行情和持仓指标）、asana001（团队和用户任务指标）。
- Agent：现有修复后的正交探索 BestFGS；预测扩展关闭；没有修改算法源码。
- 模型：deepseek-flash，thinking 关闭，temperature=0；每题最多 200 次工具、400 回合、1 小时；单 worker 顺序运行，独占分配 CPU 8、9，避开当前 LongCLI 的 CPU 0–7。
- 解题：Cube 原生隔离命令环境，不运行 Docker。最终 `/app/<题目>/<题目数据库>.duckdb` 随冻结产物回传。
- 评分：学院服务器，使用固定官方源码中未改写的 duckdb_match 和 compare_pandas_table；标准答案不送入解题环境，不在解题过程中反馈成绩。

## 验收

本地和 Cube 均通过 122 项候选源码回归与 5 项部署检查（零真实模型请求）。两题通过读库、宿主/网络/标准答案隔离、设备读写、工作区 checkpoint/restore、管道非零状态识别、进程锁、独立 DBT 建表和原始项目 dbt parse。

初次导出运行时的 `/dev/shm` 不可写，导致 DBT 进程锁 PermissionError。仅修复本试跑私有根目录的共享内存权限（1777），重新验证并封存；旧检查保存在 Cube 的 pre-shm-repair 中。不能把初次 parse 失败当成题目错误。

评分器的参考自匹配为 1，缺表反例为 0；两题未修改起始数据库均为 0。两个 Cube 零 API 夹具的冻结产物经过回传、SHA256 校验、解包和官方函数评分后仍为 0，这些记录不是模型解题结果。

原先考虑的 playbook001 起始数据库已得 1 分，未调用模型，已排除；学院 initial-qualification 保留这一记录。不能计作 Agent 成功。

## 来源与局限

官方源仓库：https://github.com/xlang-ai/Spider2 ，commit cafb867313aab4e674652054198f383cf4018943。

Google Drive 下载不可达，数据库取自 Harbor 固定镜像：https://huggingface.co/datasets/harborframework/harbor-datasets ，commit 82d1fb0c144d28b1fd9852006cee0a39e74bd4a8；逐文件验证镜像声明的大小和 SHA256；与官方评测参数核对一致。但尚未验证与 Google Drive 原文件逐字节相同。

DockerHub 拉取不可用，所以使用已有公共 Ubuntu/Python 3.12.3 镜像，在专属 venv 安装 duckdb 1.2.2、pandas 2.2.3、dbt-duckdb 1.9.6；这与官方基线 Python 3.11 不完全相同。Asana 的公开 dbt 包预装并带入，解题命令网络关闭。启动数据库未改写。

## 启动与记录

运行 Start-Spider-Smoke.ps1，在本地隐藏输入本次 API 密钥。不从其他实验复制密钥、不在聊天中输入；远端仅保存在私有 tmpfs，worker 结束删除。脚本验证封存输入并检查模型可用性，随后创建两次真实解题。不得重复启动已领取的任务。

解题进程在 Cube 持续运行；回传和评分由本机 Python relay 完成，不使用 GPT 轮询自动化。本机必须保持联网且不休眠才能及时回传和评分；若本机离线，云端解题可以继续，但不能保证即时评分。恢复时运行 relay.py，只收集已有产物，不自动重跑题目。

进度：paired-status.json；题目证据与成绩：received/<job>/。preflight-0.json、grading-acceptance.json、evidence/asset001.json、evidence/asana001.json 都属于零 API 验收证据，不是正式成绩。
