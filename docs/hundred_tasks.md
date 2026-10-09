# 百题扩展与可复用生成入口

用户在2026-10-09要求将15题扩充到100题。当前目标按总数100处理：保留T01—T15，新增T16—T100。此处的数量是任务实例，不是独立实验、独立推理类型或合格训练轨迹数量。

本轮采用服务器本地Qwen3.5-27B，关闭思考模式。通过本机回环API生成公开题目，默认引擎为vLLM；也提供使用现有CUDA12.4环境的Transformers适配器。不调用DeepSeek，不使用外部凭证，不执行模型产生的代码。当前助手负责阅读题目、核对材料与审查评分规则，三个subagent按材料分组复核。公开标题和问题不由助手代写；需要改题时记录反馈并调用模型重新生成，保留被拒版本。

## 材料与任务关系

17份已审查故障来源分别整理为一个材料包，每包保留A1—A4四个完整周期以及共享参考实验R1/R4。参考记录ID不表示健康类别。每包五个调查目标，覆盖后续周期的一致性、工况依赖、实测子系统参与、负载服务范围或参考记录适用性；具体组合由已有数据及证据限制确定。

所有时间计算使用原始时间戳，行号保持原始全局索引。名义阶段是文档背景，不等于实际动作或指令日志。参考中位数仅是可复核锚点，不能证明整个阶段内每一个样本都相同，也不能充当唯一正确分析路径。解题Agent只获得中立目录、通道字典、名义计划和通用查询工具，不获得参考窗口、数值、源文件标签和评分表。

同类能力会在不同来源上重复测量；同包题、相同来源的相邻周期和共享参考之间存在依赖。不能把100题称为100次独立实验，不能按题随机拆分训练/验证/测试。当前批次用于开发，正式划分必须先按原始来源及共享参考重做隔离。

## 服务器入口

工作目录为`/home/xjshang/hangtian_material_pipeline`，设置`PYTHONPATH=src`，Python为`/home/xjshang/anaconda3/bin/python`。

1. `scripts/prepare_hundred_materials.py`从已固定哈希的原始CSV整理17包材料并独立复核中位数。它不生成公开题目。
2. `scripts/verify_autonomous_windows.py`核查保存数组上的统计与质量操作。
3. `sbatch scripts/run_hundred_qwen.sbatch`申请1张A100 80GB，最多四个并发生成请求，作业结束关闭服务。每包结构失败最多三次，全部请求与原始响应保存。
4. 审阅整批题面、完整公开附件与后台rubric。修改提示词或传入`--feedback <JSON> --cases pack_XX ...`另开作业重生成；不覆盖先前响应。跨包重复实例需要明确其数据差异，不能仅凭字符串不同判断多样性。
5. 对合格版本保存逐题审查理由和结果型评分规则；`scripts/finalize_hundred.py`核对哈希、API原文、材料验证和完整85题覆盖后合并旧15题。

仅重生成一个被退回的任务时可用`--tasks T38 --feedback <JSON>`。必要时加`--runtime-config configs/qwen_h100_authoring.example.json`并在`sbatch`指定空闲H100。适配器只绑定127.0.0.1，要求显式关闭思考且使用指定模型；Transformers的JSON格式由提示词要求、返回后结构校验，不声称具有vLLM的语法约束。实际引擎、库版本、GPU、请求和原始响应分别记录。

混合选取已审模型版本的次序为：

1. `scripts/overlay_local_tasks.py --manifest <材料manifest> --base <整批作业目录> --replacement <单题作业目录> --out <新候选目录> --required-tasks T38`。精确检查替换集合，只复制API原对象；新题缺失、手改或材料哈希不符时拒绝写出。
2. 当前助手阅读逐题审查和评分建议后，使用`scripts/bind_hundred_reviews.py --expansion <扩展目录> --selection <材料到候选目录的JSON映射> --reviews <三份审查JSON> --approve-reviewed-outcomes`。这个开关表示已经完成实质审核；脚本只负责序列化和门禁，不会自动判定语义质量。缺少完整公开对象、材料或来源版本的审查绑定时拒绝通过。
3. `scripts/finalize_hundred.py --old <旧15题目录> --expansion <扩展目录> --selection <同一映射> --out <新的100题目录>`。新评分规则必须包含同一份总政策，旧15题保留历史审核；随后用`report_hundred_review.py`生成逐题审查HTML。

审查文件的`public_project_digest`及`material_project_digest`统一使用`hangtian.data.digest`。原文件字节SHA256、紧凑JSON的SHA256与项目digest分别命名，不相互冒充；修改题面、附件或材料必须重新审核。

新增通用约束在`prompts/batch_diversity.md`，与原自主出题规则共同使用。它不含题号、特定源文件标签或参考答案。材料中的目标和参考事实属于当次私有输入。

## 交付与状态

最终输出包括`tasks.json`、`questions.html`、`generation_provenance.json`、各包私有审查/评分文件、材料来源索引和验证结果。`tasks.json`是机器读取的题库；HTML供人阅读和搜索。Pi工具桥按私有manifest定位服务器数据，模型不会获得其中的路径和标签。

数据复算、代码测试、助手审题和独立Agent实跑是四件不同的事。旧15题有一轮运行记录且结果不全正确；新增85题尚无解题轨迹。该生成批次不会自动把候选题当作正确训练样本，也不提供通过率或难度校准结论。

## 本轮交付结果（2026-10-09）

`runs/autonomous_tasks_100_final_001/`已生成总计100题，新增85题来自A100上Qwen3.5-27B的非思考API响应（165713、165799），原15题保持历史版本。三个subagent分组审核、当前助手复核，71份模型原评分作实质修订。100题均经过Pi加载门禁，111项代码测试及离线smoke通过。新增85题仍未Agent实跑。

查看`questions.html`、`tasks.json`、`review_report.html`和`publication_verification.json`。H100兼容性/ECC失败、排队取消和被退回候选均保留；这些不计为成功出题。实际执行源代码快照位于`runs/autonomous_tasks_100_001/generation_jobs/165799/code_snapshot/`。生成失败现在返回非零进程退出码，不能仅凭调度器的历史退出码认定模型任务成功。
