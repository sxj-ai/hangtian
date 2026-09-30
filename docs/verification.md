# 验证、防泄漏与审计

## 不同的“通过”必须分别命名

| 状态 | 说明 | 不能替代 |
|---|---|---|
| schema_valid | 对象格式、枚举、字段合法 | 数值和语义正确 |
| recomputation_pass | 重新读取同一源快照计算一致 | 独立实现核验、物理真值 |
| critic_pass_pending_solver | 代码门槛和语义出题审核通过 | Agent 真能完成、有高质量轨迹 |
| fixture_only | 合成/固定响应测试通路 | 真实模型表现或真实数据结果 |
| solver_validated（预留） | 独立 Agent 实际执行与证据审核通过 | 跨实验泛化已被证明 |

当前不会直接导出 `solver_validated`。`submit_report` 返回 `submitted: true` 也只表示收到了答案。

## 已实现硬检查

严格 JSON Schema 禁止多余字段。案例与任务必须引用当前 package，fact ID 必须存在。数值 oracle 由封闭 query 复算，不执行模型编写的代码。每个任务需要唯一 local ID，数值 answer_key 不冲突；重复 task_type、事实集合与测量结构会拦截一类换皮任务。

文件版本由哈希绑定，模型调用前后可重读核对。来源组跨 split 和相同原始字节被错误分组会阻断。公开输出为白名单，不序列化整个 Case 或私有 evaluator。

Critic 必须完整覆盖各题，每题一个 verdict；blocking issue 不能同时 accept 或 basic_only。语义评论不能覆盖硬错误。

## 需要明确承认的缺口

代码不能单靠字段白名单保证自然语言题面未抄入正确答案；模型可能直接写出某个正确数值或隐藏诊断，需要语义和人工核查。哈希只能找完全相同字节，发现不了所有切片或标准化副本。固定测量定义也不能自动验证所有替代窗口合理性。

当前复算与事实构造共享 `evaluate` 实现，单元测试只是额外解析例子，不是全套独立验证器。对真实数据的重要指标应写第二实现/人工对照；正式论文不能把共享实现的自洽包装成独立审计。

默认同一模型承担生成与审查，有相关偏差。需要从接受、拒绝和修订样本中分层抽样，由领域人员或另一模型独立复核，记录错收与错拒。不要只用同模型 Critic 分数作为最终质量指标。

## 权限和安全

真实数据、本地路径、隐藏标签、评测答案、API key、权重和日志不进 Git。API key 从环境变量读取，不保存在配置或日志。网络默认关闭；两个显式开关分别确认使用远程 API 和允许数据出站。HTTP 重定向不跟随，防止授权头意外转发。

示例 API endpoint 是用户配置的 HTTPS 地址。改变地址意味着新的数据目的地，操作者应重新确认授权。不能把未经授权的真实遥测发送给第三方，即使它只是统计值。

CSV 元数据、参考文本和模型输出都按不可信数据对待。提示词不得把它们升级成系统指令。工具端必须执行权限边界，不能只靠“请勿访问私有标签”的一句 prompt。当前 `TelemetryTools` 限定源 ID、窗口、通道、读取行数及允许操作，并在提交后停止。

## 审计目录

```text
artifacts/run-id/
  summary.json
  public_tasks.jsonl          # 临时公开格式，不等于发布授权
  basic_tasks.jsonl           # 可选：基础检查任务
  private/
    run.json                  # 配置、版本、哈希
    source_manifest.json      # ID 到本地文件的私有映射
    candidates_EXP_*.json
    packages/*.json
    cases/*.json
    drafts/*_r*.json
    reviews/*_r*.json
    calls/*.json              # 仅在线模式
    evaluators.jsonl
    decisions.jsonl
    failures.jsonl
```

`public` 只是 solver 可见视图，不代表获得了数据公开发布许可。无记录时某些 JSONL 文件可能不存在。重复运行要求新目录，防止覆盖证据；当前不提供崩溃续跑。

## 将来轨迹审核

真正接入 Pi Core 后，应分别记录工具调用合法性、观察重放、数值正确性、事实引用支持度、语义结论、完成状态、成本和不确定性。不要要求轨迹与作者预设顺序完全相同；只要依据充分、权限合法、高效完成任务，就应允许不同工具路径。

失败轨迹同样保留。Benchmark 不能只保留做成功的任务，也不能因某个教师做不出来就认定任务本身无效。任务无效与求解器失败要独立归因。
