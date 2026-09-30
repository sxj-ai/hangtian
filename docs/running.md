# 运行手册

## 1. 安装（Python 3.11+）

在仓库根目录运行：

```bash
python -m venv .venv
# Linux / macOS
source .venv/bin/activate
# Windows PowerShell 使用：.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

这是以仓库为根的研究开发安装。提示词和配置留在仓库顶层；从其他目录运行时显式设置 `--project-root`，并传完整 config 路径。当前没有声称已完成独立 wheel 资源分发。

## 2. 不调用 API 的验证

```bash
python -m pytest -q
python -m hangtian.cli run \
  --manifest examples/synthetic/manifest.json \
  --config configs/pipeline.example.json \
  --backend mock \
  --out artifacts/offline-001
```

示例是 60 行人工合成数据，包含状态改变、尖峰、重复时间和指定通道全零段。模型角色由 `MockModel` 固定响应代替。结果一律 `fixture_only`；不意味着模型成功率或科研数据质量。

同一个非空输出目录禁止重用。第二次使用 `artifacts/offline-002` 等新路径，而非覆盖上次记录。窗口以记录行数计，不把每行擅自当 1 秒。

## 3. 接入自己的 CSV

复制 `configs/dataset.example.json` 为本地文件，例如 `configs/dataset.local.json`。修改 telemetry_path、时间字段、channels、辅助表、experiment_id、lineage_group 与 split。

现有 HPC 数据无须搬到 GitHub。模板中所有单位默认 null；不能凭名字自行确认单位或电流符号方向。对照 `docs/data_and_mining.md` 校准 detector 参数，另存 `configs/pipeline.local.json`。直接套用合成阈值只能做接口测试，不能当正式挖掘。

先使用 mock 运行以检查输入、对齐、候选、事实与导出。此时虽然使用了真实输入，模型部分仍是 fixture，不是合格真实任务。

## 4. 显式启用 DeepSeek

确认允许把所选事实包发送到配置的服务后，在自己的终端设置密钥。不要把 key 发到聊天、写进配置、提交 GitHub。

```bash
# Linux/macOS，静默输入，不写进 shell history
read -rsp 'DeepSeek API key: ' DEEPSEEK_API_KEY; echo
export DEEPSEEK_API_KEY

python -m hangtian.cli run \
  --manifest configs/dataset.local.json \
  --config configs/pipeline.local.json \
  --backend deepseek \
  --allow-remote \
  --allow-data-egress \
  --out artifacts/online-pilot-001
```

PowerShell 可在当前会话以环境变量设置 `DEEPSEEK_API_KEY`；不要把真实值保存成仓库脚本。`.env.example` 只是说明，本程序不自动加载 `.env`。

三个角色的 model 默认均为 `deepseek-flash`。默认 max_cases=6、max_revisions=1、max_api_calls=40；调用预算包含网络重试。第一轮是小规模开发试产，没必要一上来跑全量。当前没有精确美元费用熔断；请求/token 上限也不等价于固定费用。

初次在线调用应检查响应中的 model、JSON 模式支持、usage、finish_reason 和 private/calls 日志。本次仓库初始化没有使用用户密钥运行真实 API，所以服务端兼容性还需要这轮 smoke test 验证。

## 5. 查看结果与失败

`summary.json` 的候选数、候选组数、已处理组数、提案数、导出数和失败数含义不同。修订版本会增加 task_proposals；不能直接把提案数当最终独立任务数。

退出码 0 表示本次已处理组没有记录 package 级失败，不表示有合格任务；全被 Curator 拒绝也可能返回 0。退出码 2 表示输入错误或有失败包。`unprocessed_groups>0` 表示预算导致部分候选没进入模型，不是漏扫数据。

`private/failures.jsonl` 用于追踪错误。认证/权限失败不应通过不断重试解决；检查环境变量和数据出站授权。数据超出上限应调整资源与配置或开发分块处理，不可静默截断。

## 6. JSON Schema 和工具后端

```bash
python -m hangtian.cli schemas --out artifacts/schema-export
```

`contracts.py` 是契约单一来源，`schemas/*.schema.json` 是版本化导出，测试检查两者一致。修改输出字段时必须同步导出并更新测试。

`TelemetryTools(data, public_task)` 实现工具权限和真实本地计算。它尚未注册进 Pi Core；不要把 task factory 的日志当成 Agent trajectory。正式接入时，应由 harness 调用工具，并保留每次真实 Observation。
