"""Independent pandas replay of this audited pilot, separate from engine statistics.

Checks all scalar facts and the arithmetic/lineage rubric. Epistemic limits remain
audited source interpretations, not computationally proven physical ground truth.
"""
import argparse
import json
import math
from pathlib import Path

import pandas as pd


def main(material_path: Path, out: Path):
    material = json.loads(material_path.read_text())
    frames = {}
    for p in material["provenance"]:
        t = pd.read_csv(p["telemetry_path"])
        c = pd.read_csv(p["context_path"])
        assert t["Time"].equals(c["Time"])
        a, b = p["source_rows"]
        frame = pd.concat([t.iloc[a:b].copy(), c.iloc[a:b].drop(columns="Time")], axis=1)
        frame["seconds"] = (pd.to_datetime(frame["Time"]) - pd.to_datetime(frame["Time"]).iloc[0]).dt.total_seconds()
        frames[p["record_id"]] = frame
    results, values = [], {}
    for fact in material["facts"]:
        q = fact["query"]
        frame = frames[q["record_id"]]
        region = frame if q["region"] == "full_cycle" else frame[frame["Irradiation"] == 300]
        sample = region
        if q["slice"] == "last60s":
            sample = region[region["seconds"] >= region["seconds"].iloc[-1] - 59]
        elif q["slice"] in ["before_recovery30", "after_recovery30"]:
            run = (region["P_SA"] > 5).rolling(20, min_periods=20).sum().eq(20)
            ending_pos = next(i for i, hit in enumerate(run.to_numpy()) if hit)
            first_pos = ending_pos - 19
            sample = region.iloc[first_pos-30:first_pos] if q["slice"] == "before_recovery30" else region.iloc[first_pos:first_pos+30]
        if q["op"] == "first_sustained":
            assert region["seconds"].diff().iloc[1:].gt(0).all()
            run = region[q["channel"]].gt(q["threshold"]).rolling(q["min_records"], min_periods=q["min_records"]).sum().eq(q["min_records"])
            positions = [i for i, hit in enumerate(run.to_numpy()) if hit]
            value = None if not positions else float(region["seconds"].iloc[positions[0] - q["min_records"] + 1] - region["seconds"].iloc[0])
        else:
            value = float(getattr(sample[q["channel"]], q["stat"])())
        expected = fact["result"]["value"]
        passed = value is None if expected is None else value is not None and math.isclose(value, expected, abs_tol=1e-6, rel_tol=0)
        rows = [int(sample.index[0]), int(sample.index[-1]) + 1]
        passed = passed and rows == fact["result"]["source_rows"]
        results.append({"fact_id": fact["fact_id"], "pass": passed, "engine_value": expected,
                        "independent_value": value, "source_rows": rows})
        values[fact["fact_id"]] = value
    v = values
    arithmetic = {
        "C_timing": "supported" if v["E3_C94_solar5"] > v["E2_C1_solar5"] and v["E3_C94_solar5"]-v["E3_C94_load_on"] > v["E2_C1_solar5"]-v["E2_C1_load_on"] else "refuted",
        "C_threshold": "supported" if all(abs(v[r+"_solar10"]-v[r+"_solar5"]) <= 1 for r in ["E2_C1", "E3_C94"]) else "refuted",
        "C_energy": "supported" if (all(v["E2_C1_"+c+"_post"]>v["E2_C1_"+c+"_pre"] for c in ["P_SA", "P_BCR"])
            and all(0<v["E2_C1_"+c+"_post"]<v["E2_C1_"+c+"_pre"] for c in ["I_BAT2", "I_BAT3", "I_BAT4"])
            and abs(v["E2_C1_I_Load1_post"]-v["E2_C1_I_Load1_pre"])<=0.01) else "refuted",
        "C_environment": "supported" if all(v["E2_C1_"+c+"_post"]==v["E2_C1_"+c+"_pre"] for c in ["Irradiation", "Incidence_Angle"]) else "refuted",
        "C_persistence": "supported" if all(v[r+"_solar5"] is None and v[r+"_tail_load"]>1 for r in ["E1_C2", "E1_C3", "E1_C4"]) else "refuted",
        "C_references": "supported" if all(v[r+"_solar5"] is not None for r in ["E1_C1", "E2_C1", "E3_C94"]) else "refuted",
        "C_independence": "refuted" if len({p["series_id"] for p in material["provenance"] if p["record_id"] in ["E1_C2", "E1_C3", "E1_C4"]}) == 1 else "insufficient",
    }
    rules = [{"interpretation_id": r["interpretation_id"], "pass": arithmetic[r["interpretation_id"]] == r["expected_verdict"],
              "independent_verdict": arithmetic[r["interpretation_id"]]} for r in material["interpretations"] if r["interpretation_id"] in arithmetic]
    report = {"method": "Independent pandas read/rolling/median from original CSVs; no material engine imports.",
        "facts_checked": len(results), "all_facts_pass": all(r["pass"] for r in results), "facts": results,
        "computable_interpretations": rules, "all_computable_interpretations_pass": all(r["pass"] for r in rules),
        "noncomputable_audit_items": [r["interpretation_id"] for r in material["interpretations"] if r["interpretation_id"] not in arithmetic],
        "limitation": "Noncomputable audit items reflect unavailable logs/topology and reviewed inference limits; this replay does not independently establish a physical cause."}
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k not in ["facts", "computable_interpretations"]}, ensure_ascii=False))
    if not report["all_facts_pass"] or not report["all_computable_interpretations_pass"]:
        raise SystemExit(2)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--material", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    main(a.material, a.out)
