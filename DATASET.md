# 航天电源数据：XJTU-SPS

XJTU-SPS 数据集**不存放在本仓库**，只保存在 HPC：

```text
~/llm_datasets/XJTU-SPS
```

本仓库只保留 `DATASET_MANIFEST.json`，记录当时从 HPC 数据目录复制快照时的文件清单。

- 文件数：**364**。
- 文件内容总大小：**5,420,627,249 字节**（约 **5.42 GB**，按所有路径分别计数；部分目录包含相同文件的不同任务视图，路径总大小不等于去重后的存储量）。
- 不同 SHA-256 内容：**327** 份。
- 格式：120 个 CSV、120 个 PKL、96 个 PDF，以及 ZIP、说明文本和随附脚本。
- 原始实验：23 组；其中正常来源 6 组，故障来源 17 组。

数据目录包含：

- `original data/`：原始实验及对应工况、标签等文件。
- `XJTU-SPS for MR/`：工况识别视图。
- `XJTU-SPS for AD/`：异常检测视图。
- `XJTU-SPS for FD/`：故障诊断视图。
- `XJTU-SPS for F or R/`：预测或重建视图。

以上目录存在共享原始来源，不能直接把不同目录当成彼此独立的实验。

## 完整性验证

`DATASET_MANIFEST.json` 包含每个原文件的相对路径、字节数和 SHA-256。在能访问数据的机器上：

```bash
python scripts/verify_dataset.py ~/llm_datasets/XJTU-SPS --verify DATASET_MANIFEST.json
```

校验程序仅按字节读取文件，不加载或执行 PKL、随附脚本或 PDF 内容。

## 数据来源

数据项目说明：<https://diyi1999.github.io/XJTU-SPS/>。数据文件的版权和使用条件以原始发布方说明为准，请到该页面获取数据，不要把数据重新提交到本仓库。

## 历史说明

早期提交（`d9994ba`）曾用 Git LFS 在本仓库保存过一份数据快照，现已移除。从旧提交检出时请设置 `GIT_LFS_SKIP_SMUDGE=1`，避免下载约 5 GB 数据。
