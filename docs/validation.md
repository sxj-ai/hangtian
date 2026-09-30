# 本次初始化验证记录

日期：2026-09-30。验证环境为本次隔离 Python 运行环境，不是用户的 HPC。

## 实际执行

- `python -m pytest -q`：**51 项通过**。测试没有访问真实 API。
- `python -m hangtian.cli run --manifest examples/synthetic/manifest.json --backend mock --out artifacts/validation-001`：实际执行完成。
- 源码通过 Python 编译检查；运行时契约与 schemas 导出由测试比较。

## 合成演示计数

```json
{
  "mode": "mock",
  "status": "fixture_only",
  "counts": {
    "experiments": 1,
    "candidates": 7,
    "groups": 4,
    "processed_groups": 4,
    "deferred_or_rejected_cases": 0,
    "task_proposals": 8,
    "exported_tasks": 8,
    "failed_packages": 0,
    "unprocessed_groups": 0
  },
  "limitations": [
    "No real Agent rollout is executed by this task factory.",
    "Mock outputs test contracts only; critic approval is not final task correctness.",
    "Source-level lineage checks cannot discover unregistered cropped or transformed duplicates."
  ]
}
```

这些数量只能证明代码与固定 fixture 可以衔接，不是实际模型生成质量、不是真实案例库规模，也不是 XJTU-SPS 结果。Mock 角色输出为手写响应，语义评分不具备评价含义。

## 未做

没有使用用户 DeepSeek 密钥，没有真实服务端响应或费用；没有连接 HPC 读取原始 CSV；没有加载历史 16 个开发案例；没有运行 Pi Core、采集真实 Agent 轨迹、训练模型或计算 Benchmark 成绩。

GitHub Actions 文件已提供；本地通过不能代替远程 CI 状态。远程工作流实际结果以 GitHub Actions 显示为准。
