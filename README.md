# Hangtian — Evidence-Grounded Telemetry Task Factory

从航天遥测中挖掘可审计的 **Case**，制造有实质差异、可验证的 **Agent Task**。先建设数据与任务制造流程，后续再接入真实 Agent 轨迹、SFT 和独立 Benchmark。

> **v0.1：研究原型，不是已经验证的航天诊断系统。** 本版包含实际代码、三个英文角色提示词、JSON 契约、合成演示及测试。尚未接入用户 HPC 的真实 CSV、调用真实 DeepSeek API 或运行 Pi Core 教师。Mock 通过不等于模型通过，Critic 通过不等于任务已经由独立 Agent 验证。

## 核心流程

```text
Local telemetry + explicit lineage manifest
  -> deterministic candidate detectors
  -> bounded event grouping
  -> recomputable fact package
  -> LLM Case Curator
  -> LLM Task Generator
  -> code gates + source-snapshot recomputation
  -> LLM Task Critic -> bounded revision
  -> provisional task library + private evaluators + audit records

Next: Teacher Agent + Pi Core + read-only tools
  -> real tool-call trajectories -> independent review -> SFT / benchmark
```

候选位置 ≠ Case，Case ≠ Task，一题多次执行 ≠ 多道题。历史对话中的 4,130 个工况/标签切换位置不等于案例上限，也不是本仓库本次复算的结果。

## 快速运行

Python 3.11+，在仓库根目录：

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
python -m hangtian.cli run \
  --manifest examples/synthetic/manifest.json \
  --config configs/pipeline.example.json \
  --backend mock \
  --out artifacts/offline-001
```

离线命令不需要密钥、不调用模型 API。60 行合成 fixture 的输出全部标记 `fixture_only`。在线调用需要配置密钥和两个显式出站开关，见[运行手册](docs/running.md)。非空输出目录不会被覆盖。

## 三个英文 Prompt

| 角色 | 职责 | 核心约束 |
|---|---|---|
| [Case Curator](prompts/case_curator.md) | 判断材料是否构成有价值的分析场景 | 事实引用、候选不当真值、accept/defer/reject |
| [Task Generator](prompts/task_generator.md) | 提出 0–3 个实质不同的任务和私有评分规格 | 不凑题数、不泄露答案、不生成可执行代码 |
| [Task Critic](prompts/task_critic.md) | 审查可解性、证据边界、重复和分析价值 | 独立上下文、不能覆盖硬错误、不给虚假的质量保证 |

初版三个角色均配置 **DeepSeek V4.1 Flash**。官方当前 API 别名是 **`deepseek-flash`**，不是 `deepseek-v4.1-flash`。各角色可独立替换配置；非兼容 API 需替换 `RoleModel` 适配器。别名并非不可变权重版本，须记录返回模型、时间及请求元数据。[官方依据与核对范围](docs/sources.md)。

## 已实现与边界

| 模块 | 已实现 | 仍需完成 |
|---|---|---|
| 数据 | 显式 manifest、原序读取、辅助表对齐、来源哈希和 split 检查 | 真实数据通道/单位确认、衍生近重复追溯 |
| 候选挖掘 | 工况切换、中位数突变、孤立尖峰、选定通道全零、时间质量 | 漂移、多周期、跨源参考、稳定对照 |
| 事实包 | 可复算查询、统计、背景和限制 | 真实阈值校准、领域解释审计 |
| 三阶段制造 | 角色接口、JSON Schema、硬门槛、Critic、有限修订 | 真实 API 集成 smoke test、任务质量评测 |
| 工具后端 | 有范围限制的只读 Python 工具、Observation 收据 | Pi Core 注册、真实模型多轮执行 |
| 导出 | solver 视图与私有答案分离、失败和修订记录 | 独立解题验证、完整训练/Benchmark 发布 |

当前数值复算共享同一计算实现，不冒充完全独立的双实现核验。结构检查和 Critic 均不能消除全部语义泄漏，正式数据需人工及跨模型抽查。

## 文档导航

- [概念与范围](docs/concepts.md)：固定 Case / Task / Trajectory 层级。
- [详细 Method](docs/method.md)：问题定义、算法、信息隔离、三阶段协议和研究假设。
- [数据与 Case Mining](docs/data_and_mining.md)：真实 CSV 如何接入、检测器与校准要求。
- [Task Factory](docs/task_factory.md)：三个 Prompt 的输入输出、编译与模型替换。
- [验证与审计](docs/verification.md)：硬检查、语义评审、权限和剩余缺口。
- [实验设计](docs/experiments.md)：基线、消融、独立质量审计、来源划分及指标。
- [运行手册](docs/running.md)、[本次验证记录](docs/validation.md)、[资料来源](docs/sources.md)。

## 数据放在哪里？

核心流程支持把真实数据保留在 HPC 或本地，通过显式 manifest 引用。XJTU-SPS 数据集**不再存放在本仓库**：它保存在 HPC 的 `~/llm_datasets/XJTU-SPS`，原始发布方说明见 [DATASET.md](DATASET.md)，逐文件来源清单（路径、字节数、SHA-256）见 [DATASET_MANIFEST.json](DATASET_MANIFEST.json)，可用 `scripts/verify_dataset.py` 校验。数据不代表已完成案例挖掘、真实流程接入或独立训练／测试划分。私有答案、运行日志、密钥和模型权重同样不在本仓库中。

> 早期提交（`d9994ba` 起）曾以 Git LFS 保存过该数据快照，当前版本已移除；从旧提交检出时请设置 `GIT_LFS_SKIP_SMUDGE=1`，避免下载约 5 GB 数据。

本仓库的方法和 taxonomy 是研究设计，不预先宣称论文创新、实验提升或足够的数据规模。完整相关工作对照和真实实验仍待开展。
