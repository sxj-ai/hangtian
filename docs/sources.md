# 依据与核对范围

核对日期：2026-09-30。区分既有对话、外部公开资料和本仓库新增设计。

## 项目自身资料

用户提供的对话文件《粘贴的文本 (1).txt》是目标、术语和历史审计记录的来源。仓库不上传完整对话、SSH 日志或用户服务器路径。历史报告的 23 组实验、4,130 个切换位置和 16 个开发案例没有在此次初始化中重新复算。它们不进入本次验证成绩。

本仓库新增的 detector 原型、角色契约、受限编译、状态体系、方法公式和实验计划，是研究设计与实现，不能回写成原论文已提出的结论。

## 官方接口

- [DeepSeek V4.1 Flash 官方发布说明](https://www.deepseek.com/en/news/deepseek-v4-1-flash/)：确认发布及 `deepseek-flash` 调用别名。模型的宣传性 benchmark 结果不证明它适合本数据集。
- [DeepSeek 首次 API 调用](https://api-docs.deepseek.com/)：兼容消息接口、endpoint 和模型调用方式。
- [JSON Output](https://api-docs.deepseek.com/guides/json_mode/)：JSON object 输出要求与限制；本地仍必须验证 schema。
- [Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode/)：思考模式参数。本原型为结构化生成显式关闭，不采集供应商 reasoning_content。

这次是文档核对，不是拿用户 key 做在线集成测试。别名可变化，实验记录仍需保留返回模型和请求元数据。

## 方法参考与限制

- Liu et al., **APIGen: Automated Pipeline for Generating Verifiable and Diverse Function-Calling Datasets**, arXiv:2406.18518. [论文页面](https://arxiv.org/abs/2406.18518)。公开摘要明确区分格式、实际执行、语义三个验证层面。本项目借鉴这种分层思想，但不把函数调用数据验证等同于完整遥测调查正确性。
- Liu et al., **ToolACE: Winning the Points of LLM Function Calling**, arXiv:2409.00920. [论文页面](https://arxiv.org/abs/2409.00920)。公开摘要提出多 Agent 生成及规则/模型结合的验证。本项目参考职责分离，不把模拟对话当作真实工具轨迹。

上述两项在本次核对的范围是公开摘要及其清楚支持的总体机制；没有声称本次完成了完整正文、附录、代码的复现，也没有声称这是穷尽相关工作的综述。后续写正式论文前，需进一步精读并对照时序任务生成、Agent 数据合成和遥测系统知识，建立更充分的差异论证。
