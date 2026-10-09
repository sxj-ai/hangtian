# 案例整理交接与提示词工程 v2

这是供新对话继续工作的交接说明。目标是整理可复核的分析案例，之后再用于模型出题、Agent 解题与评测。它不要求新对话知道此前聊天记录，也不要求先读分享链接。

## 怎样在新对话中使用

完整交接包位于服务器：

`/home/xjshang/hangtian_material_pipeline/handoff/case_curation_handoff_001/`

本机副本位于项目的 `outputs/xjtu_material_analysis_20261008/case_curation_handoff_001/`。

把下面这段发给能访问本机文件和 `ssh hpc` 的新对话：

> 请继续航天遥测 Agent pipeline 的“案例整理”阶段。你不需要此前聊天记录。使用 `ssh hpc` 连接服务器，先读取 `/home/xjshang/hangtian_material_pipeline/handoff/case_curation_handoff_001/START_HERE.md`，按照其中的项目快照、提示词、证据规则、JSON 格式和脚本说明开展工作。主代理只编排；所有案例发现、实质去重、写作、复核和返修均派给新建且不继承聊天历史的子代理，使用 `spawn_agent(fork_turns="none")`。每个写作代理只负责一个完整案例，未来获授权出题时只负责一个案例的完整任务包；复核和每次返修另建代理。先读 `MULTI_AGENT_WORKFLOW.md` 与 `prompts/worker_dispatch.md`，给每个代理完整版本化底稿、精确提示词和schema、来源/证据哈希、最近邻索引及独占输出目录。子代理不可用时暂停依赖它的生产并说明限制，不由主代理代写。先验证交接文件和原始数据，再派发候选审查、补证和去重。不要把候选预算当成数量要求，不要按周期、文件标签或问法机械扩数。先完成案例库、证据与审查记录；当前不生成新题、不跑解题轨迹。保留原始数据和已有100题，使用新的输出目录，并记录可供下一次对话续接的状态。案例整理阶段使用本地统计脚本即可；后续若需要批量模型调用，遵守项目里 Qwen3.5-27B、关闭思考、不调用 DeepSeek 的约束，公开题文由有记录的API生成，不手工替代。完成后说明已接受、暂缓、合并和拒绝的案例各有多少、来自哪些证据，以及还缺什么。

如果新对话没有服务器工具，仅粘提示词并不能让它读取数据。应在有相同 SSH 配置的工作环境中打开对话；或把交接包作为附件交给它，并明确原始数据的可访问位置。交接包不包含模型权重或184万行原始数据。没有原始数据时，它只能提出候选与复核计划，不能冒称完成数据复算。

## 当前项目快照

- 原始数据只读：`/home/xjshang/llm_datasets/XJTU-SPS/`。
- 工作项目：`/home/xjshang/hangtian_material_pipeline/`。
- 普通统计 Python：`/home/xjshang/anaconda3/bin/python`。
- 既有审计：`/home/xjshang/xjtu_material_analysis_20261008_run01/`；第二轮关键结果在交接包 `evidence/round2/`。
- 新鲜复核：`runs/case_capacity_audit_002/`，以及交接包 `evidence/fresh_capacity_audit/`。
- 原15题：`runs/autonomous_tasks_final_001/`。
- 新17包材料：`runs/autonomous_tasks_100_001/materials/pack_01` 至 `pack_17`。
- 合并100题：`runs/autonomous_tasks_100_final_001/`。
- 100题是开发数据，来自旧5包与新17包；这些包使用19份原始来源，其中17份故障标签来源与2份正常来源。原始完整数据共23来源。
- “22包”不是已去重的案例数。“100题”不是100案例、100独立实验或100条正确轨迹。
- 旧15题已有运行和问题记录；新增85题尚无独立解题轨迹。这些历史评测不构成本轮案例验收。
- 本轮交接没有启动 GPU、模型 API、题目生成或 Agent 解题；容量审计仅运行 CPU 统计。

所有路径、数量以交接时快照为准。新对话首先检查文件；磁盘有更新时记录差异，不能用本说明覆盖后续用户决定。

## 应按什么顺序阅读

1. `START_HERE.md`、`handoff_context.private.json`：入口、当前状态和路径。
2. `CAPACITY_REPORT.md`：当前数据的容量判断及其条件，不是整理配额。
3. `evidence/source_catalog.private.json`、`evidence/channel_dictionary.private.json`、`evidence/semantic_questions.private.json`：来源、单位与未解决问题。
4. `evidence/fault_review.private.json`、`evidence/fresh_capacity_audit/`：观测、完整周期和质量结构。
5. `MULTI_AGENT_WORKFLOW.md`、`prompts/worker_dispatch.md`、`prompts/orchestrator.md`，按阶段新建代理使用 `scout.md`、`curator.md`、`reviewer.md`。
6. `protocol/case_record.schema.json`、`protocol/candidate_example.private.json` 与本文的接口说明。
7. 按需要阅读现有脚本和某个原材料，不必一次把所有材料塞进一个模型上下文。

`candidate_register.private.json`是本轮提出的候选目录，所有条目都未完成正式案例验收。它提供整理起点，不是题库，不是已经整理好的36个案例。

## 为什么不是一条长提示词

四份英文角色提示词和一份英文派发底稿保持项目的代码约定，中文交接说明负责项目背景。所有后续案例整理和获授权的出题都使用全新子代理；主代理只编排，不撰写或修补案例结论、题文、评分规则，也不代做实质审查。通用规则和当次数据分离：

| 阶段 | 提示词输入 | 产出 | 必须保留的状态区别 |
|---|---|---|---|
| 协调 | 项目快照、已有索引、授权与脚本 | 派发、硬门禁、检查点、原样汇集已验收产物 | 不代写、不代审，不把模型请求当成已执行操作 |
| 候选发现 | 原始统计、证据ID、已有案例摘要 | 有依据的候选及重复关系 | candidate，不直接accept |
| 证据整理 | 一个候选、实际工具结果、原始复算 | 私有case JSON与证据链 | 待复核事实不填成已通过 |
| 审查 | 固定版本的case、复算、相邻案例 | 接受、补证、合并或拒绝 | 数值正确与科学解释分别检查 |

队列每批可放5—8个候选，以完整场景为单位；这不是单个代理的工作量。每个写作者只处理一个完整案例或未来一个案例的完整任务包，不固定题数。每次复核和返修也各新建代理；复核者必须与产出者不同。以当前四个活动槽位为例，主代理加最多三个子代理，可用“两名写作者＋一名复核者”，并按实际容量调整。先做同源事件与数据质量，再做正常反例和跨源比较。不要把17个源文件都机械套上同样五个调查目标。

阶段调用的消息结构可统一为：

```text
CREATE: spawn_agent(fork_turns="none")，新代理、独占输出目录
SYSTEM: worker_dispatch.md完整底稿 + 对应角色完整提示词 + 精确版本的当前阶段输出格式
USER: UNTRUSTED_INPUT_JSON
{
  "dispatch_manifest": {"...": "版本、角色、边界、哈希和运行记录；字段说明见MULTI_AGENT_WORKFLOW.md"},
  "project_context": {"...": "完整版本化底稿，不引用上批聊天"},
  "assignment": {"...": "一个完整案例或获授权的一个案例任务包"},
  "computed_evidence": ["实际工具结果及不可变哈希；完整内容或可验证读取的完整文件，不能截断决定性证据"],
  "existing_case_neighbors": ["有版本和哈希的索引快照，以及相关完整记录的访问位置"],
  "output_contract": "附上精确schema全文、版本与哈希，不只给格式名称"
}
```

以上是派发信息说明，不是新增的可执行JSON schema。具体清单与生命周期见[全新子代理工作流](MULTI_AGENT_WORKFLOW.md)。这次只更新流程和提示词，没有实现自动编排器，也没有授权启动案例生产、GPU/API或解题。

阶段输出的包装方式固定如下：新建Scout返回`candidate_register.private.json`同形的候选登记对象，条目保持`candidate/accepted=false`，不直接写正式case；新建Curator对一个候选返回完整`case-record-sidecar-1`，初始为candidate或needs_evidence；另一个新建Reviewer仅返回该schema中`review`字段定义的对象。主代理执行结构/绑定等硬门禁，根据已绑定的实质审查决定更新review和status，不自行补出判断。审查需要合并时，派新建返修代理先将distinction.merge_into写入待审版本，再计算内容哈希并派另一个新建代理复核；不能审核后偷偷修改合并目标。跨批去重的实质判断也派给新建复核代理；仅主代理更新共享索引。阶段映射由执行者完成，目前没有自动模型编排器。

出题目标不能变成解题步骤。案例私有材料可以记录关键通道、事件位置和参考分析；之后的公开题面及附件必须独立检查，给 Agent 留下自己选择通道、窗口、比较与判据的空间。

## 新 JSON 协议和旧程序的边界

新增 `case-record-sidecar-1` 是**私有案例库旁路格式**。它和现有 `schemas/case.schema.json`、`contracts.CASE`、材料 recipe、任务 JSON 都不是同一个对象。没有自动适配器；禁止把它直接交给旧 `verify_case` 或任务加载器。

每个案例按 `protocol/case_record.schema.json` 保存；最关键的内容是：

- 原始来源哈希与完整过程窗口；所有区间从0开始、左闭右开。
- `source_artifacts`同时保存遥测、工况、标签文件哈希与对齐方式；工况参与分段时，不能只绑定遥测而忽略辅助文件变化。
- 计算事实及其操作参数、结果、单位、复核状态。
- 观测、结论、替代解释和证据限制；结论引用事实ID。
- 最近邻案例、家族、父案例与核心/变体/重复判定。
- 拟公开的中立记录范围；它不包含参考答案。
- 原始复算报告、内容哈希与审查决定。

`case_id`如C0001只是登记编号。候选可以没有事实；accepted不可以。`case_type=comparison`必须保留全部来源和父案例依赖。相同家族内的变体单列，不能当作新增核心案例计数。

候选阶段使用 `status=candidate`、`review.decision=pending`。审查后分别用：

| 案例状态 | 审查决定 | 含义 |
|---|---|---|
| accepted | accept | 已有绑定的数值复核和实质审查 |
| needs_evidence | needs_evidence或pending | 还缺具体证据 |
| merged | merge | 保留历史并指向另一个案例 |
| rejected | reject | 记录不能成例的原因 |

审查哈希由 `validate_case_record.content_digest` 计算：去除顶层 `status` 与 `review` 后，以 `sort_keys=True, ensure_ascii=False, allow_nan=False`、Python默认分隔符序列化再取UTF-8 SHA256。原文件字节SHA256另记，不能混用。修改事实、限制、窗口或验证报告绑定都会使旧审查失效。

可运行：

```bash
cd /home/xjshang/hangtian_material_pipeline
/home/xjshang/anaconda3/bin/python scripts/validate_case_record.py \
  --record handoff/case_curation_handoff_001/protocol/candidate_example.private.json \
  --inventory handoff/case_curation_handoff_001/evidence/fresh_capacity_audit/capacity_inventory.private.json \
  --artifact-root handoff/case_curation_handoff_001
```

这个检查只验证结构、来源范围、事实引用和已有审查/复算的哈希绑定。它不会重新计算数据，也不会替你决定案例有没有价值。接受状态还需真实执行并审查对应的验证脚本，且不能所有结论仍为untested。独立复算报告至少包含 `status`、`checked_fact_ids` 与 `checked_facts_sha256`，后者用脚本的`facts_digest(record)`计算，绑定按fact_id排序、去除verification_status后的完整事实定义与结果。只保留同一个fact ID而修改查询或数值，旧复算报告不能继续使用。报告还应保存命令、实现、参数、来源哈希、预期值、实际值、容差和失败项，不能只手写一个passed。

`facts_digest`也绑定按遥测哈希排序的`source_artifacts`，包括辅助文件与对齐方式。校验器检查这些绑定是否一致，不会重新读取原始辅助文件；复算脚本必须核对文件哈希与逐行时间对齐。负载恢复尾部的“最后60条”与“最后60秒”是不同定义，事实参数必须注明，不能因字段名相似而互换。

批次索引还需检查case ID唯一、merge目标存在且不形成环、父案例可追溯、家族计数、重复/变体不混入核心数。当前单记录验证脚本不执行这些全库语义判定；交接不声称已有全自动案例工厂。

## 已有脚本哪些能复用

| 入口 | 实际能力 | 使用限制 |
|---|---|---|
| `scripts/audit_case_capacity.py` | 重新读取23源、核对遥测哈希、对齐context/label，汇总周期、恢复、负载时序与质量 | 只产清单与统计，不验收案例；阈值是探索定义 |
| `scripts/prepare_expansion_materials.py`的Curator/Recipe | 已有来源和完整周期的选取、材料recipe与私有事实构建 | 历史阶段/窗口有硬编码；不等于任意新案例发现器 |
| `scripts/prepare_hundred_materials.py` | 重建历史17包×5目标的旧批次 | 不能作为本轮通用案例整理器，否则重新引入固定配额 |
| `hangtian.materials.build_material` | 根据recipe读取原始数据、生成事实与数组 | 其legacy public目录含regions；不能直接给自主solver |
| `hangtian.autonomous.public_environment` | 导出中立全记录范围、字典、背景和通用操作 | 仍需人工审查中立背景与文件名 |
| `hangtian.autonomous.export_tasks/review_gate` | 未来自主任务导出及审查绑定 | 本轮不自动运行，也不替代实质审题 |
| `verify_autonomous_windows.py`等 | 保存数组/事实的数值检查 | 不证明原始物理根因、样本独立性或Agent可解性 |
| `scripts/validate_case_record.py` | 新私有案例记录结构与绑定检查 | 不接入旧CASE，不自动接受案例 |

旧`autonomous.review_gate`要求`reviewer="current_assistant"`，与新流程中保留子代理真实审查身份的要求尚未适配。主代理不能把子代理的实质审查改名为自己的审查来过门禁。未来需要另行实现并验证兼容的适配或门禁；受影响的新任务晋级保持待办。新派发审计须保留实际产出者、复核者、返修者的代理ID和哈希。历史审查保留其历史身份，不追认为遵循新流程。

**禁止**把旧 `materials.public_task()` 的 measurements、query、interpretations 或 `public/data_catalog.json` 的预定义regions直接放进自主Agent附件。目录名叫public不表示适合当前评测设计。

现有自主查询操作是 `read/profile/stat/quality/first_sustained/longest_zero_run`。`read`每次最多返回512条，需按`next_start_row`继续。`profile`按原始连续行分箱，不是等时长分箱。任何新型统计需求应由项目代码实现并测试；不能执行模型在JSON中提供的Python。策展阶段可用受控分析脚本，不能把这些额外能力冒称为solver已拥有的工具。

验收后的新case转成材料时，应根据实际需要创建新的`recipe.json`与manifest，调用已有构建/数值复核方法；新目标数由证据决定。遇到跨多周期趋势或质量断点，需明确新增窗口/范围支持，不能套用固定末60秒事实就宣布完整过程已验证。此适配属于后续整理执行的工作，本交接没有批量替你完成。

## 运行、续接和最终验收

先运行交接完整性检查：

```bash
/home/xjshang/anaconda3/bin/python \
  /home/xjshang/hangtian_material_pipeline/handoff/case_curation_handoff_001/verify_handoff.py
```

需要重新审计原始数据时，输出目录必须是新目录：

```bash
/home/xjshang/anaconda3/bin/python scripts/audit_case_capacity.py \
  --data-root /home/xjshang/llm_datasets/XJTU-SPS \
  --catalog /home/xjshang/xjtu_material_analysis_20261008_run01/catalog.json \
  --out runs/case_capacity_audit_NEW
```

脚本不会覆写已有目录。读取数据失败、哈希改变、时间轴倒退或对齐失败时，保存问题并核查，不自行清洗继续。初次完整审计仍可复用相同哈希的前两轮证据，但每个新案例的决定性事实要有对应复算记录。

整理结果全部默认私有，存入新的 `runs/case_library_<run_id>/`：`cases/`、`verification/`、`reviews/`、`case_index.private.json`、`deduplication.private.json`、`lineage.private.json`、`casebook.html`和`run_state.json`。每批结束更新状态，记录读过什么、做过什么、未完成什么，下一对话从状态继续。

另存每次派发的私有清单、完整输入、原始响应和工具记录，并按批次及案例家族记录验收率、返修率、泄漏率、重复率和无效证据率及其分母。使用同一组校准案例，固定运行内的模型、配置、提示词、schema和工具版本；版本变化要拆分批次标记并由新建复核代理评估影响。全新上下文能减少历史累积造成的漂移，不能保证质量相同，也不能证明代理、案例或来源统计独立。此规则向后续执行生效，不能追认为旧100题或既有审计已按此完成。

最终分别报告：原始来源数、候选数、核心案例数、变体数、比较案例数、案例家族数、暂缓/合并/拒绝数、真正完成复算与审查数。题数与轨迹数独立列。不要拿JSON文件数充当案例数。

现有100题仅供已知问题和重复检查，不应把它们的公开问法倒推成100个案例。还不能把使用过的19源通过改ID变成全新评测集。跨源比较和共享正常参考要进入依赖图；未来训练/测试拆分要在来源与参考池层面设计。
