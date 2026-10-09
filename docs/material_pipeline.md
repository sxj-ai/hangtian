# 材料包、试生成任务和实际验证（v0.2）

2026-10-08 更新：用户已重新授权用 `deepseek-flash` API 批量出题，审题由当前助手完成。新增 `review_mode: assistant`，生成阶段不会调用 API 审题或解题角色。可复用提示词、材料视图和批量运行步骤见 [batch_prompting.md](batch_prompting.md)。实际 Agent 解题仍未执行。

早期三道人工草案保留在 `--stage audit --draft-index ...` 的无 API 路径中，不能算作本次 API 生成结果。程序回放参考答案不能算一次独立解题轨迹。CLI 默认阶段是 `materials`，不会默认发起网络请求。下文旧版兼容 API 路径仅描述已有能力；本次运行采用上述 flash＋助手审题路径。

本入口用于已完成数据解释审查的材料族。它补充原有 `run`，不改变原有单文件挖掘流程。运行地点是用户的 HPC；原始数据只读。

## 输入和输出

研究者先提供私有 recipe：记录来源与哈希、完整周期原始行范围、比较记录选择理由、通道说明、允许的统计查询、解释判断的依据与边界、各类任务必须覆盖的证据。`scripts/prepare_solar_pilot.py` 是一个已经审查过的低辐照材料实例，不代表全部故障类型都已自动整理完毕。

程序从原始遥测和工况文件逐行核对时间戳，保留顺序、缺采间隔和重复记录。它提取完整周期，在确定的窗口重新计算事实。材料包包含多记录上下文，生成模型不需要从几十万行 CSV 中猜测材料的含义。

每个 case 输出：

| 文件 | 用途 | 能否给解题模型 |
| --- | --- | --- |
| `private/material.json` | 内部材料、计算事实、解释边界、来源追溯 | 否 |
| `public/data_catalog.json`、`public/records.json` | 匿名化记录目录、原始顺序的选定完整周期 | 是，按题目范围访问 |
| `public/tasks.json`、`public/T01.json` 等 | 题面、测量定义、需要判断的陈述、允许的数据 | 是 |
| `private/trajectory_T01.json` 等 | 实际模型的查询、工具观测、最终答案 | 验证后台使用 |
| `validation_results.json` | 每题数值、引用、解释判断及语义复核结果 | 否，含参考答案 |
| `bundle.private.json` | 材料＋生成过程＋任务＋轨迹＋验证的完整汇总 | 否，含答案与来源 |
| `summary.json` | 数量和实际运行状态 | 可供查看 |

JSON 是主要交换格式；真实遥测仍来自原始 CSV。不要把带答案的汇总 JSON 当作解题模型的输入。

## 服务器运行

配置四个角色的兼容 Chat Completions HTTPS 地址、环境变量名称、模型标识和令牌上限。真实调用需要同时指定 `--allow-remote` 和 `--allow-data-egress`。不把密钥写入配置或日志。requested/response model 字段只是服务端报告的标识，不能独立证明代理后面的实际模型身份。

以下命令在部署目录运行；`PYTHONPATH=src` 无需安装本项目。Python 环境需要 `jsonschema`，测试另需 `pytest`。

```bash
python scripts/prepare_solar_pilot.py --data-root /home/xjshang/llm_datasets/XJTU-SPS --out private/inputs

# 当前使用的无 API 分支：保存本次讨论中编写的三道草案并验证
python scripts/write_solar_drafts.py --recipe private/inputs/solar_recipe.private.json --out private/inputs
PYTHONPATH=src python -m hangtian.cli material-batch \
  --manifest private/inputs/batch.private.json --config private/pipeline.local.json \
  --draft-index private/inputs/draft_index.private.json \
  --project-root . --out runs/pilot_offline_001 --stage audit

# 第一阶段完全不调用模型
PYTHONPATH=src python -m hangtian.cli material-batch \
  --manifest private/inputs/batch.private.json --config private/pipeline.local.json \
  --project-root . --out runs/pilot_001 --stage materials

# 以下 API 分支仅为以后恢复测试保留，目前没有继续运行。
# 第二阶段只出题、审题；复用同一输出目录
PYTHONPATH=src python -m hangtian.cli material-batch \
  --manifest private/inputs/batch.private.json --config private/pipeline.local.json \
  --project-root . --out runs/pilot_001 --stage generate --allow-remote --allow-data-egress

# 第三阶段继续实际解题和验证，也可直接从第一阶段运行 all
PYTHONPATH=src python -m hangtian.cli material-batch \
  --manifest private/inputs/batch.private.json --config private/pipeline.local.json \
  --project-root . --out runs/pilot_001 --stage all --allow-remote --allow-data-egress
```

批量清单采用 `schemas/material_batch.schema.json`。增加多个 `case_id + recipe_path` 即可分阶段批量运行。一个案例失败会记录错误并继续其他案例；不会把失败样本默默删除。处理是有界顺序执行，尚无分布式任务队列。现在支持阶段及每题完成后的断点续跑，尚不恢复一次未完成的模型步骤。

复用输出目录时，recipe、代码、提示词、配置及结果哈希必须一致；源 CSV 每次重新核验。任何变更需使用新输出目录，保留旧版本。模型调用预算包括传输重试及之前已发起的调用。批次中相同来源不得跨 train/validation/test 切分。

## 验证做了什么

1. 材料门槛：原始文件哈希一致、遥测与工况逐行对齐、窗口完整、引用的事实存在。
2. 出题门槛：封闭 JSON Schema、任务覆盖既定材料和比较对象、任务彼此分工明确、私有字段与来源名称不外泄，另由模型审查文字是否泄漏答案。
3. 解题：新的模型调用仅看到公开任务，通过受限查询工具读取数据；不传入内部事实值或参考答案。模型输出的代码永不执行。
4. 硬验证：从记录重新执行每个查询，校验答案值、空值含义、工具观测哈希、引用与测量的一致性、解释判断及所需证据覆盖。
5. 语义复核：模型检查解释是否与观测相符，是否把相关性写成唯一根因，是否错把时间差写成指令延迟。硬验证失败时语义模型不能宣布通过。

`pilot_pass` 的含义是“一次实际解题通过了当前已明确的检查”，不是多次稳定通过率，也不是航天专家独立确认或跨实验泛化。默认四个角色可以使用同一模型，角色隔离不等于模型独立性。当前试题给定测量定义和判断陈述，是有引导的证据分析任务；尚未评估完全开放的自主调查。

## 扩展到更多材料时

已明确的材料族可以把源记录选择参数化，然后程序批量计算相同类型事实。新增材料族仍需先说明：哪些记录可比较、什么现象是可观察的、哪些结论不能确定、什么算合格的验证证据。不能仅用大模型把所有标签文件改写成“唯一故障根因”题。

提示词主要约束材料如何使用、任务如何提问、证据如何引用；数值计算、身份隔离、哈希检查、预算、断点与验证是程序职责。材料事实及解释边界要同时版本化。每个任务必须能回溯到材料、查询、数据来源和实际验证记录。


## 2026-10-08 自主分析目标更正

前述精确测量契约流程属于有引导任务，不能用其验收结论替代自主分析审核。当前自主任务设计与边界见 [autonomous_tasks.md](autonomous_tasks.md)。新版15题位于服务器 `runs/autonomous_tasks_final_001`；不向解题模型提供参考查询或要求唯一分析路径，独立Agent尚未运行。
