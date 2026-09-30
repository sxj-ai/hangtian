# 航天电源数据：XJTU-SPS

本仓库保存从 HPC 数据目录复制的 XJTU-SPS 数据快照。保留原文件名、目录结构和文件字节内容。

- 文件数：**364**。
- 文件内容总大小：**5,420,627,249 字节**（约 **5.42 GB**，按所有路径分别计数）。
- 不同 SHA-256 内容：**327** 份。部分目录包含相同文件的不同任务视图，因此路径总大小不等于去重后的存储量。
- 格式：120 个 CSV、120 个 PKL、96 个 PDF，以及 ZIP、说明文本和随附脚本。
- 原始实验：23 组；其中正常来源 6 组，故障来源 17 组。

## 下载完整数据

大文件通过 **Git LFS** 存储。请先安装 Git 和 Git LFS，然后执行：

```bash
git lfs install
git clone https://github.com/sxj-ai/hangtian.git
cd hangtian
git lfs pull
```

私有仓库需要具有访问权限的 GitHub 账号。网页显示的 LFS 指针不是实际数据文件；不要把只有指针的副本用于分析。

数据在 `XJTU-SPS/` 中，包含以下目录：

- `original data/`：原始实验及对应工况、标签等文件。
- `XJTU-SPS for MR/`：工况识别视图。
- `XJTU-SPS for AD/`：异常检测视图。
- `XJTU-SPS for FD/`：故障诊断视图。
- `XJTU-SPS for F or R/`：预测或重建视图。

以上目录存在共享原始来源，不能直接把不同目录当成彼此独立的实验。

## 完整性验证

`DATASET_MANIFEST.json` 包含每个原文件的相对路径、字节数和 SHA-256。

```bash
python scripts/verify_dataset.py XJTU-SPS --verify DATASET_MANIFEST.json
git lfs fsck
```

校验程序仅按字节读取文件，不加载或执行 PKL、随附脚本或 PDF 内容。

## 数据来源

保留原始数据中附带的说明与引用信息。数据项目说明：<https://diyi1999.github.io/XJTU-SPS/>。

本次操作只复制和校验数据，不清洗、不插值、不去重，也不重新划分训练或测试集。仓库中的数据文件版权和使用条件以原始发布方说明为准。
