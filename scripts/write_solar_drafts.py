"""Save the three drafts authored in the current assistant/user discussion.

This is explicit authorship, not an API generation result or an offline mock model.
"""
import argparse
import json
from pathlib import Path


TEXTS = {
    "S_timing": (
        "T01", "太阳能输出恢复较晚，时间究竟花在哪里？",
        "比较 E2_C1 和 E3_C94 的完整低辐照阶段。分别确定实测负载投入时刻与太阳能输出首次持续越阈时刻，"
        "把从阶段起点计时的结果与从负载实际投入后计时的结果区分开。比较两个记录的时间顺序和等待时长，"
        "检验太阳能输出阈值由 5 改为 10 后结论是否敏感，并判断这些时间差能否被解释为指令执行延迟。"
        "按随题测量定义取数，对列出的陈述逐项判断并引用证据；说明连续记录数与实际经过秒数的区别。",
        "需要两个实验记录的实测负载与太阳能越阈时间，背景中的名义计划不能代替实际时间。",
        "分析过程的时间分解和阈值敏感性。"),
    "S_energy": (
        "T02", "太阳能输出变化前后，各供电通道说明了什么？",
        "在 E2_C1 中，围绕所定义的 P_SA 首次持续越阈事件，比较前后各30条记录。"
        "联合检查太阳能输出、BCR输出、三路电池电流、负载电流，以及提供的辐照和角度字段。"
        "说明这些变化或不变支持怎样的供电状态解释；检验负载电流中位数差是否在0.01 A以内。"
        "区分可以直接从记录确认的关系、依赖电流方向约定的解释，以及仍需控制器日志或测量拓扑支持的判断。"
        "对列出的陈述逐项作答并引用所有相关通道的工具观测。",
        "需要联合比较八个通道的前后窗口；单看一个功率值无法排除负载变化或工况变化。",
        "分析多个通道之间的观测关系及物理解释边界。"),
    "S_comparison": (
        "T03", "跨周期和参考记录比较，能够把结论推进到哪一步？",
        "比较 G1 的四个完整周期和 E2_C1、E3_C94 两段比较记录。结合完整低辐照过程中的持续越阈结果，"
        "以及阶段末段的太阳能功率、Load1电流和BAT2电流，描述各记录的共同点与差异。"
        "检查比较窗口中的负载是否具有可比性，避免只用阶段整体中位数或单个末段数值判断。"
        "说明现有证据能确认怎样的观测表型、能否唯一确定具体故障机理，以及同次实验的后续周期能否算独立实验。"
        "窗口内未出现越阈时应保留空值含义，不得将它写成0秒或永久不恢复。",
        "需要同次实验的前后过程及两个不同时间模式的比较记录；来源名称和标签不可作为解题依据。",
        "分析比较对象、持续现象、根因不确定性和样本独立性。"),
}


def main(recipe_path: Path, out: Path):
    recipe = json.loads(recipe_path.read_text(encoding="utf-8"))
    facts = {f["fact_id"]: f for f in recipe["facts"]}
    tasks = []
    for slot in recipe["task_slots"]:
        tid, title, prompt, need, distinct = TEXTS[slot["slot_id"]]
        tasks.append({"task_id": tid, "slot_id": slot["slot_id"], "title": title, "prompt": prompt,
            "measurement_ids": slot["measurement_ids"], "interpretation_ids": slot["interpretation_ids"],
            "required_record_ids": list(dict.fromkeys(facts[f]["query"]["record_id"] for f in slot["measurement_ids"])),
            "why_data_are_needed": need, "distinctness": distinct})
    out.mkdir(parents=True, exist_ok=True)
    (out / "solar_drafts.private.json").write_text(json.dumps({"material_id": recipe["material_id"], "tasks": tasks}, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "draft_index.private.json").write_text(json.dumps({"schema_version": "0.2", "cases": [{
        "case_id": "solar_pilot", "proposal_path": "solar_drafts.private.json",
        "authorship": "Assistant-authored drafts in the current conversation, using the audited recipe. External API generation and solver tests were deferred at the user's request."}]}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"drafts_authored": len(tasks), "external_api_calls": 0}))


if __name__ == "__main__":
    p = argparse.ArgumentParser(); p.add_argument("--recipe", type=Path, required=True); p.add_argument("--out", type=Path, required=True)
    a = p.parse_args(); main(a.recipe, a.out)
