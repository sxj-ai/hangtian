# 案例整理交接：当前助手直接执行

最新范围：**只整理案例，由当前助手直接完成，不使用subagent，不调用Qwen或其他模型API。** 当前不出题，不生成任务JSON或评分规则，不跑解题轨迹。此前多代理和API出题说明已停用，不能从历史文档重新启用。

## 在新对话中使用

把交接包的`NEW_CHAT_PROMPT.txt`内容发给能访问本机和`ssh hpc`的新对话。它先读取：

`/home/xjshang/hangtian_material_pipeline/handoff/case_curation_handoff_001/START_HERE.md`

本地副本为`outputs/xjtu_material_analysis_20261008/case_curation_handoff_001/`。交接包包含背景、提示词、数据审计摘要、候选、代码快照和验证入口，不依赖旧对话。包内不含184万行原始数据或模型权重；新对话需要服务器数据访问能力。没有原始数据时只能准备候选与复核计划，不能声称完成复算。

当前对话是在修订这套交接；把启动提示词发给新对话后，它才按用户指令执行案例整理。

## 项目状态

- 服务器项目：`/home/xjshang/hangtian_material_pipeline/`。
- 原始数据只读：`/home/xjshang/llm_datasets/XJTU-SPS/`。
- 统计Python：`/home/xjshang/anaconda3/bin/python`。
- 原始审计目录：`/home/xjshang/xjtu_material_analysis_20261008_run01/`。
- 最近完整复核：`runs/case_capacity_audit_002/`，副本在包内`evidence/fresh_capacity_audit/`。
- 已核查23来源、1,848,715行、332周期：6正常来源264周期，17故障标签来源各4周期。
- 历史22材料包与100道开发题使用19个来源，不能直接换算为独立案例数。
- 包内登记36条候选，尚未作为新案例正式验收。预计先整理30—40候选、严格审核后约25—35核心案例；这是估计，不是配额。
- 历史题目位置：`runs/autonomous_tasks_100_final_001/`；历史新17包：`runs/autonomous_tasks_100_001/materials/`。只用于追溯、材料复用与重复检查，不在当前阶段改题或扩题。

旧模型调用和子代理审查保留真实历史来源；它们不是当前工作的执行方式，也不能替代新案例的证据核查。

## 阅读顺序与执行方式

1. `START_HERE.md`、`handoff_context.private.json`和`run_state.json`。
2. `DIRECT_CASE_WORKFLOW.md`、`CAPACITY_REPORT.md`。
3. `evidence/source_catalog.private.json`、`channel_dictionary.private.json`、`semantic_questions.private.json`和`KNOWN_CORRECTIONS.md`。
4. `evidence/fault_review.private.json`、`fresh_capacity_audit/`及按需读取的`round2/`。
5. `prompts/orchestrator.md`；再按阶段使用`scout.md`、`curator.md`、`reviewer.md`。
6. `protocol/case_record.schema.json`和`candidate_example.private.json`；查看候选目录后新建实际整理输出目录。

这四份英文提示词分别负责总流程、候选发现、证据写作、自查，**全部由同一助手执行**，不意味着四名代理。`MULTI_AGENT_WORKFLOW.md`与`worker_dispatch.md`仅保留已停用提示，不参与当前流程。

每次处理一个完整案例，在独立目录保存来源、关键问题、相关旧案例、证据与限制。先读取完整过程，再复算事实，最后单独自查。每5—8个候选汇总一次，但不要求达到固定接受数量。长对话恢复时从完整文件和状态继续，不能只靠旧回复的摘要。

## 案例怎么计数与验收

候选、材料包、核心案例、同族变体、多源比较、来源文件、历史题目和轨迹分别计数。换问法、周期、通道编号或窗口通常只是变体。多源比较必须增加具体分析价值，记录全部父来源与共享参考。整理完整事件或长期变化，不能为凑数量拆散同一过程。

每份案例说明：原始观测是什么、支持什么判断、为什么有意义、还不能判断什么。保留前史、变化、后续/恢复、正常参考、反例、质量问题及缺失背景。此时不写公开问题、题目槽位或评分规则。

实际数值复算与语义自查分别记录。自查者仍是当前助手，在`review.independence`填写`same-assistant self-review`及真实限制；不得写成独立代理或专家审核。另一个数值实现的复算可以称独立数值复核，同一函数重跑只能称可重复检查。

材料层面的accepted要求：完整且有实质区别的场景、可追溯并复核的事实、有限定的结论、如实的自查记录，以及正确的来源和版本绑定。它不表示独立语义审查或真实根因已经证实。缺证据就暂缓；重复则合并或记变体；无法成例则保留拒绝理由。

## JSON与验证脚本

`case-record-sidecar-1`是私有案例库格式，不是旧`contracts.CASE`、材料recipe或任务JSON；不直接送旧任务加载器。字段保留来源哈希、完整窗口、facts、claims、limitations、distinction、public_scope、verification和review。

`source_artifacts`同时绑定遥测、工况、标签文件哈希及对齐方式。原始行范围从0开始、左闭右开。`public_scope`只记录未来可用的中立数据范围，不生成公开题目，也不自动导出给解题Agent。

审查内容摘要由`validate_case_record.content_digest`计算：去掉顶层status/review，按Python的sort_keys=True、ensure_ascii=False、allow_nan=False和默认分隔符序列化，再取UTF-8 SHA256。它与原文件字节SHA256不同。

复算报告至少包括status、checked_fact_ids、checked_facts_sha256。`facts_digest`绑定按fact_id排序并去除verification_status的完整事实定义/结果，以及按遥测哈希排序的source_artifacts。修改数值、查询或辅助文件后，不能复用旧报告。报告须有真实命令、输入、操作、结果、容差和失败项，不能只手写passed。

```bash
cd /home/xjshang/hangtian_material_pipeline
/home/xjshang/anaconda3/bin/python scripts/validate_case_record.py \
  --record handoff/case_curation_handoff_001/protocol/candidate_example.private.json \
  --inventory handoff/case_curation_handoff_001/evidence/fresh_capacity_audit/capacity_inventory.private.json \
  --artifact-root handoff/case_curation_handoff_001
```

校验器只检查结构、来源范围、事实引用与审查/验证的已有绑定，不重新计算原始数据，不判断科学解释。全库的唯一ID、merge目标、环路、父来源和核心/变体计数仍需检查；当前没有全自动案例验收程序。

写作阶段输出candidate/needs_evidence；自查阶段使用schema里的review对象并绑定准确内容版本；满足实际检查后再更新accepted、merged或rejected。合并目标先写入被审版本再计算哈希。数值、窗口、结论或限制变化后，重新核查受影响内容。

## 现有脚本的适用范围

| 入口 | 可以做什么 | 限制 |
|---|---|---|
| `audit_case_capacity.py` | 核对源哈希、辅助表对齐，统计周期/恢复/时序/质量 | 只产统计清单，不验收案例；阈值是探索定义 |
| `prepare_expansion_materials.py`中的Curator/Recipe | 选已有来源和完整周期、建立recipe和事实 | 历史阶段有硬编码，不能机械套所有新场景 |
| `materials.build_material` | 按recipe构建数据数组和事实 | legacy public输出含regions/query，不适合直接作为自主解题附件 |
| `verify_autonomous_windows.py`等 | 核对保存数组上的数值 | 不替代新事实原始复算或科学解释 |
| `validate_case_record.py` | 新案例JSON结构与版本绑定 | 不接旧CASE，不自动证明正确 |

`prepare_hundred_materials.py`是重建旧17包固定目标的脚本，不是当前通用案例整理器。本阶段不运行题目生成、任务发布、API服务或Agent解题脚本，也不适配那些下游门禁。

原始数据应保持采集顺序；不要默默排序、插值、补零、去重或仅按时间戳拼表。名义阶段不等于独立指令日志，标签边界不等于真实注入时刻，中位数不代表全程，零值不证明停机，电压存在不等于负载有效工作。最后60条与最后60秒必须在参数中区分。

## 开始、续接和交付

```bash
/home/xjshang/anaconda3/bin/python \
  /home/xjshang/hangtian_material_pipeline/handoff/case_curation_handoff_001/verify_handoff.py \
  --server-paths --verify-raw
```

相同哈希的已有审计可复用；新案例的决定性事实仍需对应复算。若需要完整重审，使用新输出目录：

```bash
/home/xjshang/anaconda3/bin/python scripts/audit_case_capacity.py \
  --data-root /home/xjshang/llm_datasets/XJTU-SPS \
  --catalog /home/xjshang/xjtu_material_analysis_20261008_run01/catalog.json \
  --out runs/case_capacity_audit_NEW
```

实际案例整理存入新的`runs/case_library_<run_id>/`，包含cases、verification、reviews、case_index.private.json、deduplication.private.json、lineage.private.json、可读案例簿和run_state.json。默认全部私有。状态记录已完成、未完成、来源/提示词/工具版本及下一步。

最终按核心/变体/比较与暂缓/合并/拒绝分别报数，解释每个案例的证据意义和限制。完整案例整理完成后停在这个阶段，不自动进入出题或实验。
