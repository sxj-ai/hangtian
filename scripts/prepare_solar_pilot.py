"""Create a private audited recipe on the server, never alter raw CSVs.

This explicit recipe is one reviewed material family, not a generic 17-fault curator.
Original-source hashes pin the two completed data audits.
"""
import argparse
import hashlib
import json
from pathlib import Path


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def prepare(data_root: Path, out: Path):
    # Source identities belong only in a private runtime recipe, not solver prompts.
    sources = [
        ("SA_partial component or branch short circuit", "G1", "4c3a9420d0db36913ac08ca3ccbcdcf307d90572a9c016c5a5b22c72016a177b", "d3552e0e5048df64c3c8eff150c1786814e3def6d3811766e61fd007957c50ef",
         [("E1_C1", 1, 0, 5570), ("E1_C2", 2, 5570, 11141), ("E1_C3", 3, 11141, 16710), ("E1_C4", 4, 16710, 22281)]),
        ("2024.9.18_normal", "G2", "af66485ea401645a24b1423d0ef645845724f38c1e0cf07e47349e47284552f0", "1b5c62b4e3d44dcb80731d1a985db08e227703a468ef0a866a20f98d616abfac",
         [("E2_C1", 1, 0, 5570)]),
        ("2024.10.23_normal", "G3", "066678c5893c0250778ff6bf3c080c255203f0d4d32fd1fc6c9cb6e58bc0fe54", "37b4514626804df247e314dc2f5a5b48436f16100fc832dc020d147df42f7bfc",
         [("E3_C94", 94, 518011, 523581)]),
    ]
    records = []
    for name, group, tele_sha, ctx_sha, cycles in sources:
        folder = data_root / "original data" / name
        tele, ctx = folder / (name + ".csv"), folder / (name + "_Work_Condition.csv")
        if sha(tele) != tele_sha or sha(ctx) != ctx_sha:
            raise ValueError("Source hash does not match the audited snapshot: " + name)
        for rid, cycle, a, b in cycles:
            records.append({"record_id": rid, "series_id": group, "sequence_index": cycle,
                "lineage_group": group, "telemetry_path": str(tele), "context_path": str(ctx),
                "source_hashes": {"telemetry": tele_sha, "context": ctx_sha}, "source_rows": [a, b]})
    fields = ["U_SA", "I_SA", "P_SA", "U_Load_output", "I_Load_output", "P_Load_output", "U_BCR", "I_BCR", "P_BCR"]
    for battery in (2, 3, 4):
        fields += [f"U_BAT{battery}", f"I_BAT{battery}", f"T_BAT{battery}"]
    fields += ["U_Bus", "I_Bus", "P_Bus"]
    for branch in (1, 2, 3):
        fields += [f"U_Load{branch}", f"I_Load{branch}", f"T_Load{branch}", f"P_Load{branch}"]
    units = {"U": "V", "I": "A", "P": "W", "T": "degC"}
    channels = {c: {"unit": units[c[0]], "unit_basis": "Author code documentation; no independent calibration check"} for c in fields}
    channels.update({c: {"unit": None, "unit_basis": "Supplied context; physical scale/creation process not independently verified"}
                     for c in ("Irradiation", "Temperature", "Incidence_Angle", "Load_Signal")})
    facts, interpretations, slots = [], [], []

    def fact(rid, channel, suffix, slice_name="all", op="stat", threshold=None):
        fid = rid + "_" + suffix
        q = {"record_id": rid, "op": op, "region": "low_irr", "slice": slice_name, "channel": channel}
        if op == "stat":
            q["stat"] = "median"
            definition = f"{rid}: {channel} median in low_irr/{slice_name}; preserve all selected records."
            unit = channels[channel]["unit"]
        else:
            q.update(threshold=threshold, min_records=20)
            definition = f"{rid}: first {channel} strictly > {threshold} for >=20 consecutive records in low_irr; actual seconds since first phase record, null if absent."
            unit = "s"
        facts.append({"fact_id": fid, "definition": definition, "query": q, "unit": unit})
        return fid

    def claim(iid, statement, verdict, ids, rationale, basis="audited_evidence_boundary"):
        interpretations.append({"interpretation_id": iid, "statement": statement, "expected_verdict": verdict,
            "fact_ids": ids, "rationale": rationale, "basis_type": basis})
        return iid

    def slot(sid, focus, ids, claims):
        slots.append({"slot_id": sid, "focus": focus, "measurement_ids": ids, "interpretation_ids": claims})

    timing = []
    for rid in ("E2_C1", "E3_C94"):
        timing += [fact(rid, "I_Load1", "load_on", op="first_sustained", threshold=1),
                   fact(rid, "P_SA", "solar5", op="first_sustained", threshold=5),
                   fact(rid, "P_SA", "solar10", op="first_sustained", threshold=10)]
    timing_base = [i for i in timing if not i.endswith("solar10")]
    c1 = claim("C_timing", "E3_C94 的太阳能输出从低辐照阶段起点计时恢复更晚，因此它在负载实际投入后等待恢复的时间也更长。", "refuted", timing_base,
        "Separate phase-to-load, phase-to-solar and load-to-solar intervals. The late load onset can reverse the apparent waiting-time ranking.", "audited_comparative_arithmetic")
    c2 = claim("C_command", "可以把这些阶段起点到响应的时间差直接解释为指令执行延迟。", "insufficient", timing_base,
        "No independent command-dispatch timestamps; supplied Load_Signal provenance differs between sources.")
    c3 = claim("C_threshold", "在这两个记录中，将太阳能输出阈值从 5 改为 10 后，首次持续越阈时刻的变化均不超过 1 秒。", "supported",
        [i for i in timing if "solar" in i], "Compare measured crossing times. This only tests sensitivity in two records, not a universal fault threshold.", "audited_comparative_arithmetic")
    slot("S_timing", "区分负载投入较晚与投入后太阳能输出恢复较晚；比较阈值敏感性；不得把时间差包装成指令延迟。", timing, [c1, c2, c3])

    energy = []
    for channel in ("P_SA", "P_BCR", "I_BAT2", "I_BAT3", "I_BAT4", "I_Load1", "Irradiation", "Incidence_Angle"):
        for sl, suffix in (("before_recovery30", "pre"), ("after_recovery30", "post")):
            energy.append(fact("E2_C1", channel, channel + "_" + suffix, sl))
    c4 = claim("C_energy", "在选定前后窗口中，P_SA 和 P_BCR 的中位数增加，三路电池的正向电流中位数均降低，而 I_Load1 中位数相差不超过 0.01 A。", "supported", energy[:12],
        "Compute all six paired channel comparisons. Under the documented sign convention this is consistent with less battery discharge while the load persists; not a full power-balance proof.", "audited_comparative_arithmetic")
    c5 = claim("C_environment", "选定前后窗口的 Irradiation 和 Incidence_Angle 中位数均保持相同。", "supported", energy[12:],
        "Only median equality in these windows is tested; it does not prove every sample or unobserved physical environment is unchanged.", "audited_comparative_arithmetic")
    c6 = claim("C_mechanism", "这些观测已经足以唯一确定造成太阳能输出变化的具体控制器动作或物理根因。", "insufficient", energy,
        "Co-occurrence of power/current changes does not identify controller state or an intervention; controller logs/topology are absent.")
    slot("S_energy", "用太阳能、BCR、电池及负载的联合变化解释供电贡献变化，并检验工况中位数是否改变；限定机制解释。", energy, [c4, c5, c6])

    comparison = []
    for rid in ("E1_C1", "E1_C2", "E1_C3", "E1_C4", "E2_C1", "E3_C94"):
        # Reuse timing facts instead of duplicating evidence under new IDs.
        solar_id = rid + "_solar5"
        if solar_id not in {f["fact_id"] for f in facts}:
            fact(rid, "P_SA", "solar5", op="first_sustained", threshold=5)
        comparison += [solar_id, fact(rid, "P_SA", "tail_solar", "last60s"),
                       fact(rid, "I_Load1", "tail_load", "last60s"),
                       fact(rid, "I_BAT2", "tail_bat2", "last60s")]
    within = [i for i in comparison if i.startswith("E1_")]
    c7 = claim("C_persistence", "在 G1 的 C2–C4 中，所定义的太阳能持续恢复均未在低辐照窗口内出现，同时末段负载电流中位数仍大于 1 A。", "supported", within,
        "Compare C2–C4 with C1 using crossing absence and tail load. Absence within a finite window is not permanent failure.", "audited_record_comparison")
    c8 = claim("C_references", "这里三段比较记录 E1_C1、E2_C1 和 E3_C94 均在低辐照窗口内出现了所定义的太阳能持续恢复。", "supported",
        [i for i in comparison if i.split('_solar5')[0] in ("E1_C1", "E2_C1", "E3_C94") and i.endswith("solar5")],
        "Comparison is about these selected records, not the entire normal population.", "audited_record_comparison")
    c9 = claim("C_root", "这些记录足以唯一确定一个具体的太阳能组件或支路故障机理。", "insufficient", comparison,
        "Observed persistent low output differs from recovering references, but neither source filename nor steady-state telemetry uniquely identifies a microscopic failure mechanism.")
    c10 = claim("C_independence", "G1 的 C2、C3、C4 可以作为三个独立实验来估计跨实验泛化能力。", "refuted", within,
        "Catalog explicitly identifies one series. Cycles are dependent repeats, not independent source experiments.", "audited_lineage_metadata")
    slot("S_comparison", "把主记录的完整过程与同次实验前序周期、两种对照比较；识别持续低输出表型，并检验根因与独立重复的证据边界。", comparison, [c7, c8, c9, c10])

    recipe = {"schema_version": "0.2", "material_id": "M_solar_low_irr_001", "data_origin": "real", "split": "development",
        "title": "低辐照阶段：恢复时序、供电变化与持续低输出的证据边界",
        "low_irradiation_value": 300, "records": records, "channels": channels, "facts": facts,
        "interpretations": interpretations, "task_slots": slots,
        "public_background": [
            "本材料含三个实验序列的六个完整周期。G1 的 C1–C4 来自同一次连续实验；G2、G3 是不同实验序列的选定比较周期。ID 不表示健康类别。",
            "保留完整周期和原始采集顺序。low_irr 是工况字段 Irradiation=300 的完整连续段。该数值只用于定位已记录工况，未将其作为健康阈值。",
            "名义周期为5700秒：低辐照阶段名义起点2100秒、终点3000秒。名义计划、提供的 Load_Signal 和实测电流是不同证据；独立指令发送日志不可用。",
            "按作者模型采用电池正向电流表示放电的约定；这里只观测 BAT2、BAT3、BAT4，不能把它们当作所有储能支路。",
            "first_sustained 按真实时间戳计算经过秒数；20条连续记录不等于20秒。空值只表示在给定窗口内未观测到该事件。",
            "before_recovery30 和 after_recovery30 分别取 P_SA 首次连续20条大于5时刻的前30条和从该时刻开始的30条；这是基于观测的比较窗口。",
            "last60s 取该阶段最后时间戳向前59秒以内（含端点）的全部记录。缺采间隔、重复时间戳都会保留并报告。"
        ],
        "limitations": ["Work_Condition生成过程、控制器状态和详细测量拓扑未知。", "比较记录经过目的性选择，不代表总体分布。", "G1只有一次实验，三个后序周期不是三个独立故障样本。", "文件标签仅作内部来源追溯，不是题目中可直接推断的唯一根因。", "功率与电流间存在派生关系，不能把各通道当作完全独立证据。"],
        "forbidden_public_strings": [name for name, *_ in sources] + ["short circuit", "支路短路", "组件短路", "_AnomalyLabel", "/home/", "source_hashes"],
        "selection_rationale": "Purposeful selection from completed audit: same-source pre/post cycles plus early-load/late-recovery and late-load normal references. No random-sample or cross-source-generalization claim.",
        "evidence_sources": ["Previous raw audit: 23 sources, 332 cycles, hashes pinned.", "Second targeted audit: all 264 normal low-irradiation intervals contain sustained recovery; semantics remain bounded.", "Author PhyGNN battery-current convention and SpaceHMchat channel-unit documentation; no independent hardware calibration."]}
    out.mkdir(parents=True, exist_ok=True)
    (out / "solar_recipe.private.json").write_text(json.dumps(recipe, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "batch.private.json").write_text(json.dumps({"schema_version": "0.2", "cases": [
        {"case_id": "solar_pilot", "recipe_path": "solar_recipe.private.json"}]}, indent=2), encoding="utf-8")
    print(json.dumps({"records": len(records), "facts": len(facts), "slots": len(slots), "interpretations": len(interpretations)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    prepare(args.data_root.resolve(), args.out.resolve())
