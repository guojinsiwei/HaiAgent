# 全站仪团队

KZDSH — 改进前冻结基线

本仓库保存 **KZ 接入 DeepSeek Harness（DSH）的迁移版**，版本号 `0.3.0`。
它对应 2026-10-18 LongCLI 算法改进前后对比实验中的 **baseline**。
源码沿用本次探索机制改动前冻结的实现，未包含 `exploration-v2` 的新触发、
测量判读、结果利用和退出机制改进。这里保留的是 KZDSH，仍依赖官方 DSH。

## 内容

- `src/`：KZ 策略、记忆、探索、Monitor、Advisor、Critic、完成审查与 DSH 集成。
- `config/`：可移植配置模板。
- `scripts/`：配置生成、宿主版本检查及历史离线审计入口。
- `tests/`：冻结版本的回归测试。
- `package-lock.json`：与固定 DSH 版本匹配的依赖锁。
- `PROVENANCE.json`、`SOURCE-MANIFEST.json`：版本来源与文件 SHA-256。

历史审计脚本可能引用未收录的实验材料；日常验证使用下述直接测试命令。
本仓库仅包含源代码与离线开发材料，运行凭据通过环境变量单独配置。

## 安装与验证

要求 Node.js 24 或更新版本，固定宿主依赖为 `@deepseek-ai/dsh@0.2.0-rc.2`。
原生 shell 集成建议使用 Linux 或 WSL。

```sh
npm ci
npm run check:host
node scripts/verify-snapshot.mjs

node --test --test-concurrency=2 \
  tests/policy.test.mjs tests/exploration-trigger.test.mjs \
  tests/exploration-learning.test.mjs tests/strategy-execution-repair4.test.mjs \
  tests/full.test.mjs tests/recovery-clock-repair5.test.mjs \
  tests/recovery-integration-repair5.test.mjs tests/subgoal-integration-repair5.test.mjs \
  tests/transport-recovery.test.mjs
```

该组测试在实验服务器实际 DSH 依赖下 **111/111 通过**，没有模型调用。
`npm test` 运行全部历史测试；此前 Windows 全集有 25 项已知失败，涉及旧审查
夹具、符号链接权限及历史子目标预期，不能将其表述为全集通过。

## 接入 DSH

```sh
node scripts/prepare-config.mjs
# LongCLI 使用原题 INSTRUCTION.md，且部署环境支持 POSIX Bash 时：
node scripts/prepare-config.mjs --longcli
```

脚本生成 `.runtime/kz.patch.yml` 与 `.runtime/transport.patch.yml`，配置会指向
当前检出的绝对插件路径。生成配置不会启动模型调用。

运行时设置 `KZ_WORKSPACE` 为独立题目工作目录，`KZ_AUDIT_DIR` 为其外的审计目录；
按任务设置 `KZ_TASK_INSTRUCTION_PATH`。DSH 的 `headless` 配置应依次加载
`config/common.patch.yml`、自行配置的模型路由、生成的 transport 与 KZ 配置。
模型路由、密钥、账户计费与外部调度器需要由部署方配置。

**模板内保留历史默认值**（800 次请求、600 次工具、50 元成本策略等），
用于忠实保存冻结版本；本次配对实验的实际控制为每次最多 4 元、12 次合计
最多 48 元，依赖仓库外的独立预算控制器。直接使用模板不会自动获得该实验
控制器的全轮预算保护。部署前应按实际模型、额度与执行环境设置预算。

## 版本与协作

原始冻结清单的 66 个文件（源码、测试及 package.json）已逐个核对一致。
本仓库只增加分享说明、依赖锁、校验脚本和清单，不修改基线算法。
离线测试通过不代表解题效果；旧新版的效果以独立配对实验结果为准。
