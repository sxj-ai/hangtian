# Hangtian — Evidence-Grounded Telemetry Task Factory

从航天遥测中整理可审计的 **Case**，生成有实质差异、可验证的 **Agent Task**。本项目首先建设任务制造流程；轨迹采集、SFT 和独立 Benchmark 是后续阶段。

> **v0.1 / research scaffold**：本仓库区分已实现代码、合成数据验证和真实数据实验。合成演示不是 XJTU-SPS 实验结果；模型评审通过也不等于任务已通过独立解题验证。本文不是已被实验支持的论文结论。

## 核心流程

```text
Local CSV + explicit source/lineage manifest
  -> deterministic detectors -> bounded event grouping
  -> recomputable fact packages
  -> LLM Case Curator
  -> LLM Task Generator
  -> deterministic checks + reference recomputation
  -> LLM Task Critic -> bounded revision
  -> candidate task library (pending solver validation)

Later: Teacher Agent + Pi Core + read-only tools
  -> real tool-call trajectories -> independent verification -> SFT / benchmark
```

候选位置不是案例，案例不是任务，重复执行不是新任务。现有对话中的 4,130 个工况/标签切换位置只是一种历史索引，不是案例上限，也不是本仓库已复算的结果。

## 三个模型角色

| Role | Responsibility | Must not do |
|---|---|---|
| Case Curator | 判断材料是否构成可分析场景，绑定事实和证据边界 | 编造事实、单位、因果或故障根因 |
| Task Generator | 生成少量实质不同的任务及私有验证规格 | 换皮扩写、泄露答案、生成任意可执行代码 |
| Task Critic | 审核可解性、证据边界、任务差异和分析价值 | 覆盖代码硬错误、把自己的评分当作最终真值 |

三个角色使用独立上下文，初始均配置 DeepSeek V4.1 Flash；角色、供应商和模型参数可以独立替换。官方当前调用别名是 **`deepseek-flash`**，并非 `deepseek-v4.1-flash`。别名可能变化，因此实验需记录返回模型、时间、配置和可用的后端标识。见 [官方发布说明](https://www.deepseek.com/en/news/deepseek-v4-1-flash/) 与 [API 文档](https://api-docs.deepseek.com/api/create-chat-completion/)（核对日期：2026-09-30）。

## 阅读顺序

1. [概念与研究边界](docs/concepts.md)
2. [Method 设计](docs/method.md)
3. [Case Mining 与数据接入](docs/data_and_mining.md)
4. [Task Factory 与英文提示词协议](docs/task_factory.md)
5. [验证、审计和防泄漏](docs/verification.md)
6. [实验设计与实现路线](docs/experiments.md)
7. [运行手册](docs/running.md)

## 数据放在哪里？

核心流程支持把真实数据保留在 HPC 或本地，通过显式 manifest 引用。另按仓库所有者要求，本仓库在 [`XJTU-SPS/`](XJTU-SPS/) 保存一份完整数据快照，大文件使用 Git LFS；共 364 个原始文件路径，内容总大小为 5,420,627,249 字节。下载方式见 [DATASET.md](DATASET.md)，逐文件来源清单见 [DATASET_MANIFEST.json](DATASET_MANIFEST.json)。数据快照不代表已完成案例挖掘或独立训练／测试划分。私有答案、运行日志、密钥和模型权重不属于本次数据快照。

代码框架和三阶段闭环可以先写、先用合成数据测试；实际检测阈值、辅助表对齐、通道单位、同源关系和任务价值，必须再用真实 CSV 及说明文件校准。目录检查或历史聊天摘要不能替代本次实际验证。

## 状态与承诺

本次初始化将补齐可运行的离线演示、受限计算器、模型适配器、测试和详细文档。正式数据量、任务合格率、模型表现及论文创新性均不预先宣称。使用外部模型前须配置自己的 API key 并明确允许网络调用和数据出站；离线测试不调用付费 API。
