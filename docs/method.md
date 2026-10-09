# Method v0.1：事实约束的遥测 Case–Task 制造流程

> 实现补充（2026-10-08）：新增独立的 v0.2 `material-batch` 入口，支持审查后的多记录材料、实际解题调用和逐题验证。见 [材料流程说明](material_pipeline.md)。下文仍描述原有 v0.1 挖掘入口，不应把它的“尚未执行解题”限制套用到新增入口；具体真实实验结果以运行产物为准。

**状态：可执行研究原型 + 待验证的方法假设。** 本文说明接口、算法、信息流和实验要求，不宣称已经取得真实数据结果、证明创新性或达到发表标准。模型和检测器配置应版本化，不应把本稿写成已完成实验的过去时论文。

## 1. 问题定义

给定实验集合 \(\mathcal D=\{D_e\}\)，其中 \(D_e=(X_e,t_e,C_e,L_e,M_e)\)。\(X_e\) 是数值遥测，\(t_e\) 是原始采样时间，\(C_e\) 是可公开的运行背景，\(L_e\) 是私有标签，\(M_e\) 是来源、通道语义和文件版本等元数据。不是每个实验都有完整的 \(C_e\) 或 \(L_e\)。

我们的输出不是一个分类标签，而是带验证协议的任务集合：

\[
\mathcal T=\{(q_i,\mathcal O_i,\mathcal A_i,\mathcal V_i,\ell_i)\},
\]

其中 \(q_i\) 为公开题面，\(\mathcal O_i\) 为允许观察的数据范围，\(\mathcal A_i\) 为只读工具契约，\(\mathcal V_i\) 为私有计算和语义评审依据，\(\ell_i\) 为来源组。题目必须既有数据支持，又不能把私有答案提前放入公开观察。

区分两项质量目标：**authoring validity**（题面和验证规则是否成立）与 **execution validity**（独立 Agent 能否在真实环境中完成并给出正确证据）。当前实现主要覆盖前者的工程闭环；后者不得由 Critic 自行宣布通过。

## 2. 总体算法

```text
Input: explicit manifests, source snapshots, detector config, role model config
Validate schema, lineage groups, duplicate source hashes and declared split
For each experiment:
    Read declared channels in acquisition order; validate auxiliary alignment
    A <- run deterministic candidate detectors
    G <- proximity grouping with a bounded merge span
    For each selected group g under the processing budget:
        P <- compute facts, windows, available background and limitations
        C <- CaseCurator(P)
        Validate C's contract and references
        If C is defer/reject: record it; do not fabricate context
        Else:
            Reopen original files and recompute P's facts
            Repeat at most R+1 proposal attempts:
                T <- TaskGenerator(P, C, structured failure feedback)
                Apply schema, fact-reference and structural-duplicate gates
                J <- TaskCritic(P, C, T, deterministic check report)
                Validate complete review coverage and verdict consistency
                If repair requested and budget remains: record and revise
                Else: export review-passed tasks via a public-field whitelist
Record every rejection, revision, unprocessed group and source association
Output: provisional task library + private evaluators + audit records
```

对应代码：`data.py` → `mining.py` → `factory.py`；角色接口在 `models.py`，契约和硬检查在 `contracts.py`，未来 harness 可复用的只读工具在 `tools.py`。

## 3. 来源治理先于生成

同一实验的原始文件、拷贝、切片、不同问法和多次轨迹必须继承同一来源组。manifest 显式指定 `lineage_group` 与 split；代码检查同组跨 split，以及相同字节哈希被登记为不同组的错误。这个检查不能发现所有裁剪、重采样或标准化后的近重复，真实数据接入时仍须补充来源追溯。

CSV 保留原顺序；不把时间戳当唯一主键，不自动排序或删重。窗口按零基、左闭右开原始记录索引定义。缺失值不填成零，也不在计算均值时静默丢弃。带时区时间转到同一绝对轴；无时区时间保留本地相对轴，不假装是 UTC。

辅助 context 表须与遥测逐行、逐时间对应，重复时间戳不允许被普通按时间合并放大成笛卡尔积。`private_label` 文件当前只计算哈希，不进入检测和 LLM 输入；它的具体语义、对齐及用于评分的方式需另行审查。

真实数据路径、含故障名的文件名、split 和来源组不传给模型。实验 ID 和 component 描述也需人工检查，避免人为编码答案。哈希记录是数据一致性信息，不是匿名化或不泄漏的充分证明。

## 4. 多视角候选挖掘

### 4.1 已实现的候选族

1. **工况切换**：声明的 context 字段相邻记录变化，留下候选位置。这不等于执行指令到达时刻。
2. **局部中位数变化**：对通道两侧各 \(w\) 行计算中位数差，并与绝对阈值及局部 MAD 尺度比较。
3. **孤立尖峰**：中心值偏离邻居均值超过阈值，而两侧邻居彼此足够接近。
4. **选定通道连续全零**：选定列连续达到近零条件至少指定行数。除非配置覆盖所有通道，否则不能称为“全系统全零”。
5. **时间质量**：相邻重复时间和倒退。完整窗口内非相邻重复数量也可由计算器核验。

变化候选的实际规则是：

\[
|\operatorname{med}(x_{i:i+w})-\operatorname{med}(x_{i-w:i})|
>\max(\tau_{abs},k\operatorname{MAD}(x_{i-w:i})).
\]

这里 MAD 是未做高斯尺度校正的中位绝对偏差。\(\tau_{abs}\)、\(k\)、\(w\) 均为开发参数，不是论文已验证的最优值。候选位置可能早于或晚于真实物理变化点；严禁把它直接当精确 onset 真值。

### 4.2 尚未实现的候选族

缓慢漂移、同工况跨周期差异、跨实验正常参考检索、经过单位/同步核对的多通道关系、稳定运行对照等。它们列入研究 taxonomy，但不算本版已完成的算法。比如 \(P\approx UI\) 只有在单位、测点、符号方向和同步机制已确认时才适合使用；不能凭字段前缀做物理故障判定。

### 4.3 归并和覆盖

按原始记录顺序归并邻近候选，设最大合并跨度防止 A 邻近 B、B 邻近 C 最终把整个实验串成一案。单个已检测的长持续段可以超过跨度限制；限制针对候选间的扩张，不机械拆碎持续事件。

当前归并只采用时间/行距离启发式，不声称恢复真实事件因果边界。Case Curator 可以 defer，但 v0.1 不会自动响应它提出的新窗口要求。正式版本应增加受限重取窗口、组件关联、跨窗口引用与人工边界审计。

处理预算 `max_cases` 实际限制的是进入模型的候选组数量，不是承诺产生的合格案例数。未处理组单独计数。扩充规模要看事件类型、组件、工况、时长和来源覆盖，而非追求重复窗口数量。

## 5. 可复算事实包

事实包 \(P_g\) 包含来源哈希、group、context/before/after 窗口、显式通道描述、数值事实、背景变化及限制。每项事实为：

\[
f_j=(\mathrm{id}_j,\mathrm{query}_j,\mathrm{value}_j,\mathrm{unit}_j).
\]

`query` 来自封闭计算语言，而非 LLM 生成的 Python。已支持均值/中位数/极值/数量、前后均值差、重复时间数量和带明确定义的首次越阈值。当前事实构造主要使用前后统计及时间质量；不自动为所有候选制造精确起点答案。

数值、查询及稳定 ID 绑定；模型只能引用现成 fact ID。某项查询因缺失数据或时间冲突不可用时，记录不可用原因，不生成伪值。`unit=null` 明确表示未知，后续提示词不得自行补成 W、V 或 A。

后台重开原文件并复算全部事实，再编译任务的期望测量值。**这是同一计算实现的重放，不是完全独立算法实现的双重验证。** 当前单元测试用解析可知的合成数值核对；真实数据关键指标还需第二实现或人工对照，避免共享代码错误。

## 6. Case Curator：有依据地接受，也允许弃权

\(C_g=\mathcal C_\theta(P_g)\)。输出 `accept/defer/reject`，以及观测摘要、事实引用、候选解释、反证、缺失证据和限制。

与无约束出题不同，模型不能创造测量、替换标签真值或无限扩窗。案例可以是“不足以确定唯一根因”的有价值分析场景，但不能只靠“证据不足”四个字批量复制案例。必须明确哪类问题、哪些证据、哪项缺口。

同一模型分角色使用只是工程初始选择，不构成理论保证。Curator 也可能错误接受/拒绝；这些决策均需留存，不能把模型删掉的困难场景从质量分析中消失。

## 7. Task Generator：能力差异，而非换皮扩写

\(\mathcal T_g=\mathcal G_\theta(C_g,P_g,\mathcal A)\)。每次允许 0–3 个候选任务；数量是上限而非配额。类型包括状态比较、时序定位、差异性调查、证据充分性、数据质量与综合调查。

任务的实质差异应体现在目标、证据依赖、可选行动或判定标准，而非措辞。一个综合调查及其子步骤可以同时用于课程训练，但不应声称是独立案例或独立统计样本。

数值评分项只声明 `answer_key + fact_id`。后台解析事实中的查询和预期值，模型不能自行扩大容差、生成任意代码或捏造数值 oracle。其余结论用明确、允许合理替代答案的语义 rubric 审核。

公开题面应中性，例如调查某段负载行为，而非“证明这是某故障”。后台已有案例摘要和解释不自动泄漏给解题 Agent。为避免“用未公开窗口定义强行判错”，编译器公开指定测量的计算范围和定义，但不公开算出的答案。因此本版复杂度准确称为**有给定测量规范的引导式调查**。

## 8. 硬检查、Critic 与有限修订

硬检查包括契约、引用存在性、来源一致性、数值复算、任务 ID 唯一、相同任务结构重复、评分项键冲突。它们不会自动判断自然语言结论与事实之间的所有关系。

Critic 重新审核题面能否回答、是否泄漏、语义评分是否对题、是否过度推断，以及 sibling tasks 是否实质不同。其 accept/basic_only/revise/reject 必须覆盖每个任务，不能覆盖代码失败，也不能一边列 blocking issue 一边接受。

修订次数有上限。修订允许缩小目标或减少题数，禁止通过扩大数据权限、编造背景、放松容差或删除反证来“刷通过”。当前 task 级代码错误及 Critic 的 revise 可触发生成器重试；Curator 输出错误和不合法 Critic 响应记录失败，不无限自动修复。

## 9. 公开任务与私有验证器

公开输出采用字段白名单：中性题面、源 ID、允许范围、通道描述、只读工具、测量定义与报告要求。私有输出保存源映射、事实数值、期望值、rubric、模型调用记录和评审结果。字段隔离不能完全消除生成题面中的语义泄漏，仍须 Critic 和人工复查。

`TelemetryTools` 执行真实本地查询并生成 observation receipts；`submit_report` 只返回收件状态，不返回是否正确。该 Python 后端尚未接入 Pi Core 的 JS agent loop，当前任务工厂不采集真实模型轨迹。

## 10. 可证伪的研究主张与下一步

需要用实验检验而非预先认定：多视角候选是否改善覆盖，事实约束是否减少无依据题目，跨模型审查是否减少同模型偏差，保留不可识别性是否提升证据校准，结构化来源组是否减少污染。

这些不是已确立的创新点。论文还需完成充分的相关工作对照、真实数据验收、独立任务审计、真实 Agent 解题与跨来源实验。详见 `experiments.md` 和 `sources.md`。


## 已实现的材料批次扩展（2026-10-08）

上文主要描述旧版单文件工厂。本次另在材料入口实现四组已审查材料的批量出题：deepseek-flash API写题、助手逐题审查、独立原始数据复算、参考回放和错误答案负对照。共12道新增题，独立Agent解题未执行。通用提示词与材料契约分离，公开文字保持API原文并追踪到具体调用。完整方法、结果及适用限制见[批量提示词说明](batch_prompting.md)。


## 2026-10-08 自主分析目标更正

前述精确测量契约流程属于有引导任务，不能用其验收结论替代自主分析审核。当前自主任务设计与边界见 [autonomous_tasks.md](autonomous_tasks.md)。新版15题位于服务器 `runs/autonomous_tasks_final_001`；不向解题模型提供参考查询或要求唯一分析路径。在该任务设计阶段，独立Agent尚未运行；后续执行结果见下节。

## 2026-10-09：Pi Agent 实际执行

使用Pi SDK 0.87.1与服务器本地Qwen3.5-27B，关闭思考模式，完成全部15题的独立会话。模型仅能调用自由窗口telemetry_query与submit_report；没有默认终端/文件/网络工具，也不读取后台参考答案。原始运行5题提交、10题在统一20次模型请求预算内未完成。362次成功数值查询经独立计算核对一致，但提交内容仍包含语义错误，不能由工具校验推导任务或答案全部通过。

另对未提交会话进行了仅用已有证据的一次收束诊断，与原始自主结果分开计数。执行方法、完整结果、代码测试与语义审核边界见[Pi执行与审核](pi_evaluation.md)。当前实现已支持实际工具轨迹采集；高完成率、可靠语义判断、跨模型及跨来源推广仍未建立。
