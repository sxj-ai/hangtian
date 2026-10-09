"""Read-only case-capacity inventory, not case acceptance or task generation.

Recompute cycle features from every original source in acquisition order. Source
names and labels stay in private output. Thresholds are exploratory definitions,
not engineering limits. No model/network/GPU calls occur in this script.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import os

for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[variable] = "1"

def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(8388608), b""):
            h.update(block)
    return h.hexdigest()


def runs(mask):
    result, start, count = [], None, 0
    for index, value in enumerate(mask):
        count = index + 1
        if value and start is None:
            start = index
        elif not value and start is not None:
            result.append((start,index)); start = None
    if start is not None:
        result.append((start,count))
    return result


def sustained_offset(values, times, threshold, minimum=20):
    """Return first qualifying source-relative index and true elapsed seconds."""
    for a, b in runs(value > threshold for value in values):
        if b-a >= minimum:
            return {"index": a, "offset_s": float(times[a]-times[0])}
    return {"index": None, "offset_s": None}


def clean(value):
    import numpy as np
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, np.ndarray)):
        return [clean(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, np.bool_):
        return bool(value)
    return value


def write(path, value):
    path.write_text(json.dumps(clean(value), ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def audit(root, catalog_path, out):
    # Outputs cannot be nested anywhere in the read-only dataset tree.
    root, out = root.resolve(), out.resolve()
    if out == root or root in out.parents:
        raise ValueError("Output must be outside the raw dataset")
    import numpy as np
    import pandas as pd
    out.mkdir(parents=True, exist_ok=False)
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    sources, cycles = [], []
    for meta in catalog:
        path = (root / meta["raw_relative_path"]).resolve()
        if root not in path.parents:
            raise ValueError("Source outside dataset")
        if file_hash(path) != meta["sha256"]:
            raise ValueError("Raw telemetry hash changed: " + meta["source"])
        context_path = path.with_name(path.stem + "_Work_Condition.csv")
        label_path = path.with_name(path.stem + "_AnomalyLabel.csv")
        data, context = pd.read_csv(path), pd.read_csv(context_path)
        if not data.Time.equals(context.Time):
            raise ValueError("Context alignment changed")
        labels = pd.read_csv(label_path) if label_path.exists() else None
        if labels is not None and not data.Time.equals(labels.Time):
            raise ValueError("Label alignment changed")
        channels = [column for column in data if column != "Time"]
        if len(channels) != 33 or len(data) != meta["rows"]:
            raise ValueError("Unexpected raw shape")
        times = (pd.to_datetime(data.Time)-pd.to_datetime(data.Time.iloc[0])).dt.total_seconds().to_numpy()
        if not np.isfinite(times).all() or (np.diff(times) < 0).any():
            raise ValueError("Invalid or reversing time axis; preserve and investigate separately")
        irradiation = context.Irradiation.to_numpy()
        anchors = [0] + (np.flatnonzero((irradiation[1:] > 0) & (irradiation[:-1] == 0))+1).tolist() + [len(data)]
        if anchors != meta["cycle_anchor_rows"]:
            raise ValueError("Cycle boundaries changed")
        zero_ranges = runs((data[channels].to_numpy() == 0).all(axis=1))
        conflicts = []
        for stamp, group in data[data.Time.duplicated(keep=False)].groupby("Time", sort=False):
            changed = [c for c in channels if group[c].nunique(dropna=False) > 1]
            if changed:
                conflicts.append({"rows": group.index.tolist(), "changed_channels": changed})
        summary = {"source": meta["source"], "telemetry_sha256": meta["sha256"],
                   "context_sha256": file_hash(context_path),
                   "label_sha256": file_hash(label_path) if labels is not None else None,
                   "raw_relative_path": meta["raw_relative_path"],
                   "rows": len(data), "cycles": len(anchors)-1,
                   "normal_source_name": "normal" in meta["source"],
                   "cycle_anchor_rows": anchors, "all_33_zero_ranges": zero_ranges,
                   "duplicate_timestamp_extra_rows": int(data.Time.duplicated().sum()),
                   "conflicting_timestamp_groups": len(conflicts),
                   "conflict_examples": conflicts[:3],
                   "missing_measurements": int(data[channels].isna().sum().sum()),
                   "label_counts": labels.AnomalyLabel.value_counts().to_dict() if labels is not None else {},
                   "label_transitions": (np.flatnonzero(np.diff(labels.AnomalyLabel.to_numpy()) != 0)+1).tolist() if labels is not None else [],
                   "context_values": {c: context[c].unique().tolist() for c in context if c != "Time"}}
        sources.append(summary)
        for index, (a, b) in enumerate(zip(anchors[:-1], anchors[1:]), 1):
            record = {"source": meta["source"], "cycle": index, "source_rows": [a,b],
                      "low_irradiation": [], "measured_load_runs": {}}
            for lo, hi in runs(irradiation[a:b] == 300):
                lo, hi = a+lo, a+hi
                if hi-lo < 120:
                    continue
                p = data.P_SA.to_numpy()[lo:hi]
                result = {"source_rows": [lo,hi], "median_P_SA": float(np.median(p)),
                          "tail_60_records_median_P_SA": float(np.median(p[-60:])),
                          "recovery": {}}
                for threshold in (1,5,10):
                    r = sustained_offset(p, times[lo:hi], threshold)
                    result["recovery"][str(threshold)] = {
                        "source_row": None if r["index"] is None else lo+r["index"],
                        "offset_s": r["offset_s"]}
                record["low_irradiation"].append(result)
            for branch, nominal in ((1,2100),(2,4200),(3,600)):
                intervals = []
                for lo, hi in runs(data[f"I_Load{branch}"].to_numpy()[a:b] > 1):
                    if hi-lo >= 10:
                        lo, hi = a+lo, a+hi
                        intervals.append({"source_rows": [lo,hi],
                            "start_minus_nominal_s": float(times[lo]-times[a]-nominal),
                            "span_s": float(times[hi-1]-times[lo])})
                record["measured_load_runs"][str(branch)] = intervals
            cycles.append(record)
        print(json.dumps({"source": meta["source"], "rows": len(data), "cycles": len(anchors)-1}), flush=True)
    normal_names = {s["source"] for s in sources if s["normal_source_name"]}
    normals = [x for c in cycles if c["source"] in normal_names for x in c["low_irradiation"]]
    ranges = []
    for source in sources:
        selected = [c for c in cycles if c["source"] == source["source"]]
        solar = [x for c in selected for x in c["low_irradiation"]]
        recovery = [x["recovery"]["5"]["offset_s"] for x in solar if x["recovery"]["5"]["offset_s"] is not None]
        timing = {}
        for branch in (1,2,3):
            values = [r["start_minus_nominal_s"] for c in selected for r in c["measured_load_runs"][str(branch)]]
            timing[str(branch)] = {"observed_runs":len(values), "min":min(values,default=None), "max":max(values,default=None)}
        ranges.append({"source": source["source"], "recovery_5_count": len(recovery),
            "recovery_5_min_s":min(recovery,default=None), "recovery_5_max_s":max(recovery,default=None),
            "low_median_le_1_count":sum(x["median_P_SA"] <= 1 for x in solar), "load_timing":timing})
    result = {"schema_version":"case-capacity-audit-1", "status":"inventory_only_no_cases_accepted",
        "catalog_file_sha256":file_hash(catalog_path), "source_count":len(sources),
        "normal_sources":len(normal_names), "fault_label_sources":len(sources)-len(normal_names),
        "raw_rows":sum(s["rows"] for s in sources), "cycles":len(cycles),
        "normal_cycles":sum(c["source"] in normal_names for c in cycles),
        "fault_source_cycles":sum(c["source"] not in normal_names for c in cycles),
        "normal_low_irradiation_intervals":len(normals),
        "normal_low_median_le_1_count":sum(x["median_P_SA"] <= 1 for x in normals),
        "normal_recovery_above_5_count":sum(x["recovery"]["5"]["offset_s"] is not None for x in normals),
        "all_33_zero_rows":sum(b-a for s in sources for a,b in s["all_33_zero_ranges"]),
        "all_33_zero_ranges":sum(len(s["all_33_zero_ranges"]) for s in sources),
        "definitions": ["Recovery: > threshold for 20 consecutive acquisition records; true timestamps for elapsed seconds.",
            "Active load: > 1 recorded ampere for >=10 consecutive acquisition records; not an equipment limit.",
            "Tail summary uses last 60 records, not 60 seconds.",
            "Cycles are repeated measurements within sources, not independent experiments.",
            "Named normal/fault source membership is private metadata, not a measurement-certified state."],
        "sources":sources, "per_source_features":ranges}
    write(out/"capacity_inventory.private.json", result)
    write(out/"cycle_features.private.json", cycles)
    return result


if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--data-root",type=Path,required=True)
    parser.add_argument("--catalog",type=Path,required=True)
    parser.add_argument("--out",type=Path,required=True)
    args=parser.parse_args()
    audit(args.data_root,args.catalog,args.out)
