# 面向后续批量生成的提示词与验证

通用提示词负责规定“如何依据材料出题”，材料包负责说明“这一次有哪些证据、能问什么”。不能把题号、故障名、特定通道或某道题的答案写进通用提示词。当前实现使用 `prompts/material_generator.md` 的 reusable policy v4；四个材料族共享同一个系统提示词。题面只说明分析目标，精确的记录、窗口、通道和阈值放在附带的结构化定义中，避免自然语言将部分组合扩大为全部组合。

## 三层输入

1. **通用规则**：证据可追溯、题面中立、来源关系准确、测量范围闭合、判断标准明确、结论范围受限、题目有实质区别。不限于本批的某个通道、窗口或题号。
2. **材料契约**：公共背景、通道含义与单位、记录与来源关系、每个任务目标、精确测量定义、待验证命题。`generation_view()` 按任务组织精确的“记录—窗口—通道”组合，避免模型自行扩展为所有记录与所有窗口的组合。
3. **审题反馈**：错误类型、具体位置、为何违反规则。具体题号只属于本次反馈，不进入通用规则。`prompts/material_review_checklist.md` 定义九类可复用错误。

完整内部材料保留数值事实、参考判断、理由、研究动机和来源。出题视图不传预先算好的数值、参考判断、质量统计结果或可能含有结果的研究动机；它传精确测量定义与需要判断的命题，由这些命题确定任务目的。这样模型不需要把答案当成题目背景。验题端仍使用完整内部材料。此设计用于当前“有引导的证据分析题”，并不等于让模型自主发现任意新科学问题。

公开题面及待判断命题由 API 输出。程序只附加来自材料的背景、测量定义和数据访问范围；助手审题时不直接改写公开题目。需要修改时更新通用提示词或诊断反馈，再调用生成 API。

## 错误类型与执行边界

| 错误类型 | 适用规则 | 当前执行方式 |
| --- | --- | --- |
| RESULT_LEAKAGE | 不把待求结果作为已知条件 | 隐藏参考值＋字段扫描＋逐题语义审查 |
| PROVENANCE_ERROR | 不混淆记录、来源和独立实验 | 提供来源分组＋逐题审查 |
| MEASUREMENT_SCOPE_EXPANSION | 不要求定义之外的测量 | ID/引用覆盖检查＋题面语义审查 |
| UNDEFINED_CRITERION | 不使用没有标准的“相近、稳定、正常”判断 | 审查阈值、容差及命题含义 |
| PROPOSITION_DRIFT | 不改变限定条件、量词和判断含义 | 精确 ID 覆盖＋逐条语义对照 |
| UNIT_OR_TIME_ERROR | 不混淆单位、记录数、经过时间与事件标记 | 计算测试＋原始数据独立复算＋审题 |
| INFERENCE_OVERREACH | 不从局部统计推出唯一根因或系统全貌 | 依据材料边界审查 |
| UNSCORED_REQUIREMENT | 必答内容必须有证据与评分依据 | 对照查询及解释规则审查 |
| DUPLICATE_DECISION | 不把改写措辞当成新任务 | 对照任务目的和证据组合审查 |

提示词不是自动正确性保证。当前机器门槛覆盖结构、引用、数据复算和验证器行为；完整的语义审题仍由助手完成。新的故障类型或分析方法需要扩展材料契约，必要时增加受测试的查询操作，不能仅靠一句“不要幻觉”完成。

## 在 HPC 上运行一批

目录 `/home/xjshang/hangtian_material_pipeline`，解释器 `/home/xjshang/anaconda3/bin/python`。原始数据只读。先设置 `PYTHONPATH=src`。

```bash
export PYTHONPATH=src
PY=/home/xjshang/anaconda3/bin/python

# 已审查的四个材料族；只整理材料，不写公开题目。
$PY scripts/prepare_expansion_materials.py \
  --data-root /home/xjshang/llm_datasets/XJTU-SPS \
  --catalog /home/xjshang/xjtu_material_analysis_20261008_run01/catalog.json \
  --channel-recipe private/inputs/solar_recipe.private.json \
  --out private/inputs/new_batch

# 先建立实际运行材料并独立复核。
$PY -m hangtian.cli material-batch \
  --manifest private/inputs/new_batch/batch.private.json \
  --config configs/material_deepseek_flash.example.json \
  --out runs/new_batch --stage materials --project-root .
$PY scripts/verify_expansion_independently.py --run-dir runs/new_batch

# 密钥只通过环境变量进入进程，不写进 JSON、源码或日志。
read -rsp 'DeepSeek API key: ' DEEPSEEK_API_KEY
export DEEPSEEK_API_KEY
$PY -m hangtian.cli material-batch \
  --manifest private/inputs/new_batch/batch.private.json \
  --config configs/material_deepseek_flash.example.json \
  --out runs/new_batch --stage generate --project-root . \
  --backend deepseek --allow-remote --allow-data-egress
unset DEEPSEEK_API_KEY
```

配置使用 `deepseek-flash` 与 `review_mode: assistant`，实际只调用生成角色。开启同一模型的 thinking/high，JSON 输出采用官方接口支持的参数；启用 thinking 时不发送无效的 temperature 参数。参见 [DeepSeek 思考模式文档](https://api-docs.deepseek.com/guides/thinking_mode/)。日志记录完整系统提示词、输入、最终输出、请求/返回模型、用量、请求标识和哈希，不保存密钥或模型内部推理内容。预算包含传输重试；单次运行最高24次请求。开启新输出目录进行提示词实验时，应同时核查前几轮累计用量。

助手逐题检查 `candidate_tasks.json` 和内部材料，保存哈希绑定的 `private/assistant_review.submitted.json`。`reviewer` 为 `current_assistant`；绑定 `proposal_sha256`、`material_sha256`、`public_tasks_sha256`，并完整覆盖每个任务的 decision/leakage/issues/rationale。哈希采用项目的 `digest()`，不是随意对 JSON 文件字节求哈希。不得用脚本批量填 accept 代替实际阅读。然后执行：

```bash
$PY scripts/finalize_review_batch.py --run-dir runs/new_batch
$PY scripts/report_expansion.py --run-dir runs/new_batch
```

审题不通过时保留旧目录，在新的 recipe 中加入 `generation_feedback`，必要时修订共用提示词，并选择新运行目录重新生成。验收通过才发布 `public/tasks.json`。结果汇总包含公开任务、私有验证结果、API 来源记录和可阅读的题目页面。

需要保留旧轮已合格题、只更换退回题时，使用 `scripts/assemble_api_versions.py --manifest ... --out ...`。选择清单按 case 指定 recipe_path，以及每题的 task_id/source_case_dir。该程序只复制与原始 API 调用日志完全匹配的题目对象，拒绝人工改写的对象；组合后仍须独立复核与新哈希绑定审题，不能把版本选择当作自动批准。

本次最终目录为 `runs/expansion_flash_final_001`：四组材料、12道新增题；题目来源为第六轮的10个合格版本与第七轮的2个替换版本。它们使用同一个系统提示词哈希。全部探索与修订共25次生成请求、75个候选题版本；最终保留12题，不能把候选版本数当成题库规模。总用量由服务端报告为315,992 tokens，详见 `generation_provenance.json`，此处不估算账单。

验收记录：110项独立原始数据检查、145项参考测量/判断/引用检查、48项错误答案负对照通过；本地和HPC均86项测试通过。旧版离线入口另产出8个合成 fixture 任务，不计入这12题。独立Agent解题尚未执行。

## 当前适用范围

材料整理对已经审查的四族进行了参数化，出题与硬验证支持批处理；新增材料族仍需要核查来源、比较条件与解释边界。当前任务含明确测量定义和待判断命题，属于有引导的分析，不能冒充完全开放的自主调查。

四族共用一份提示词的一次运行，只验证了这四族上的表现，不证明对所有未来材料都有效。后续每批应记录各类错误、返工率、重复情况及实际 Agent 解题结果，持续修订共用规则，保留回归材料。参考答案复算通过与 Agent 独立解题成功是两个不同状态。

本轮同时调整了提示词、生成视图和思考配置，未做单因素消融，不能将改善单独归因于某一项。各题仍提供明确测量与命题，且命题判断分布不均、排列存在规律；它们适合开发流程，正式评测前应平衡/打乱命题并实测Agent表现。相邻窗口和同源案例不能按题随机拆分训练/测试集。


## 2026-10-08 自主分析目标更正

前述精确测量契约流程属于有引导任务，不能用其验收结论替代自主分析审核。当前自主任务设计与边界见 [autonomous_tasks.md](autonomous_tasks.md)。新版15题位于服务器 `runs/autonomous_tasks_final_001`；不向解题模型提供参考查询或要求唯一分析路径，独立Agent尚未运行。
