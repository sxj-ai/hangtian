# 三阶段提示词、任务编译与模型替换

## 三个角色的输入输出

| 角色 | 输入 | 输出 | 当前代码的后续行为 |
|---|---|---|---|
| Case Curator | 匿名候选、窗口、事实、背景、限制 | accept/defer/reject、假设与证据引用 | 校验；defer 不伪造补充材料 |
| Task Generator | accepted case、事实、工具能力、修订反馈 | 0–3 个候选任务及私有规格 | 代码校验和复算 |
| Task Critic | 同样事实、候选题和 code gate | 逐题判定、具体缺陷及评分诊断 | 有限修订或暂存 |

三个 system prompt 均是英文，分别位于 `prompts/case_curator.md`、`task_generator.md`、`task_critic.md`。运行时附加对应 JSON Schema，避免示例输出格式与实际解析规则漂移。模型不能自行新增 `python_code`、`expected_answer` 等字段。

每次都是独立 messages 列表，不复用前一角色聊天历史。Critic 可以看私有事实和 rubric，但不应把生成器的自信当依据。`task_language` 控制题目文字语言，不改变 schema 的英文键名和类型枚举。

当前辅助表的 `context_observations` 只给制造端看，没有通过工具开放给 solver。因此不能要求 solver 查到 `Load_Signal` 等未开放字段，也不能据此暗中评分。两个出题/审核提示词已明确这一点；要做工况—响应联合分析，必须先实现受限背景查询工具，而不是只修改题面。

## 一个具体流程（完全是合成示例）

合成记录里某段功率由 15 变为 0，另有温度尖峰及重复时间。这些都由演示脚本的数据定义决定，不是 XJTU-SPS 的测量。

程序先标记候选，再用 before/context/after 计算均值、极值和变化量。Curator 的合格输出应该是“某场景可以调查；这些事实支持什么；缺少什么”，不能直接给出唯一元件故障。

Generator 可提出“比较观测变化及多种解释”的引导式调查，并用 `numeric_checks=[{answer_key: ..., fact_id: ...}]` 指向后台已计算事实。题面不能写出正确数值。编译器把该事实的计算定义公开，例如指定窗口均值；正确值留在私有 evaluator。

Critic 检查题面是否真的对应这些计算、是否需要不存在的正常参考、不同任务是否只是换皮，以及“证据不足”是否有明确依据。其 accept 只对应 authoring review，输出状态仍是 `critic_pass_pending_solver`。

## 不是越多题越好

0–3 是候选数量上限，不是每个案例至少三题。不要为了数量把均值、差值、同一事件的复述包装成三次独立调查。现有结构签名仅拦截一部分重复；不同类型但相同语义的任务还需 Critic、人工及后续跨案例去重。

没有规定最少工具调用次数。允许高效 Agent 合并查询。复杂度要来自证据驱动的判断，而非为了“多步”人为拆开一个计算。`investigation_decisions` 是作者描述的设计意图，不是已经观测到的 Agent 行为。

## 修订循环

默认最多 1 次修订，可在有上限的配置中改变。代码引用错误会回传结构化原因；Critic 的 revise 会要求生成完整新草案。所有草案和审查结果保留，不能只保存最后通过的版本。

v0.1 以整个 sibling task batch 修订，不逐题累计“最好版本”；这需要在成本和通过率统计中如实说明。传输错误采用有限重试，认证错误等不应被反复重试。模型格式错误或无效 Curator/Critic 输出记录失败，不假装已经完成完整自修复系统。

## 模型配置

三个角色都使用官方当前模型别名 `deepseek-flash`，来源见 `sources.md`。上一版聊天出现过 `deepseek-v4.1-flash` 写法，本仓库不用它作为 API ID。

`models.<role>` 分别配置 base_url、model、api_key_env、temperature、max_tokens。同一兼容接口内换模型可改配置；供应商消息格式或参数不兼容时，应替换实现 `RoleModel` 的适配器，而不是承诺任何模型都只改一个字符串。

别名可能被服务商重定向。保存请求模型、返回模型、时间、request ID、可用 fingerprint、参数、提示词哈希和 usage。即便这些都保存了，如果服务商不提供不可变版本 ID，也不能声称模型权重严格锁定。

## 离线与在线

`MockModel` 是手写固定响应，分支用于测试 schema/审计/导出，不是 DeepSeek 的替代能力测量。mock 审查不判断质量；所有导出标为 `fixture_only`。切换到 `--backend deepseek` 后才使用模型接口，并且还须两个显式出站开关及 API key。

网络适配器使用 JSON object 输出和本地 schema 校验；合法 JSON 不等于符合 schema。它不记录供应商的 reasoning_content，只保留必要的结构化输出、请求内容和元数据。真实遥测事实包仍可能敏感，所以调用日志必须留在私有目录。
