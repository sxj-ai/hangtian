"""Conservative candidate detectors and recomputable, privacy-minimized facts."""
from __future__ import annotations

import statistics
from .data import DataError, Telemetry, digest, evaluate


def detect(data: Telemetry, config: dict) -> list[dict]:
    candidates: list[dict] = []

    def add(kind: str, start: int, stop: int, channels: list[str], rule: dict) -> None:
        item = {"detector": kind, "start_row": start, "stop_row": stop,
                "channels": channels, "rule": rule}
        item["candidate_id"] = "E_" + digest([data.sha256, item])[:16]
        candidates.append(item)

    n = len(data.times)
    for field, values in data.context.items():
        for i in range(1, n):
            if values[i] != values[i - 1]:
                add("context_transition", i, i + 1, [], {"field": field})
    for i in range(1, n):
        if data.times[i] <= data.times[i - 1]:
            kind = "repeated_time" if data.times[i] == data.times[i - 1] else "time_reversal"
            add(kind, i - 1, i + 1, [], {})
    w = config["window_rows"]
    for channel, rule in config["channels"].items():
        if channel not in data.columns:
            raise DataError("Detector references an undeclared channel")
        values = data.columns[channel]
        last_step = -w
        for i in range(w, n - w + 1):
            before, after = values[i - w:i], values[i:i + w]
            if None in before or None in after or i - last_step < w:
                continue
            med = statistics.median(before)
            noise = statistics.median(abs(v - med) for v in before)
            change = abs(statistics.median(after) - med)
            threshold = max(rule["min_step"], config["noise_multiplier"] * noise)
            if change > threshold:
                # This is a window-based candidate, NOT a precise physical onset.
                add("median_step", i, i + 1, [channel], {"threshold": threshold, "window_rows": w})
                last_step = i
        for i in range(1, n - 1):
            a, b, c = values[i - 1:i + 2]
            if None in (a, b, c):
                continue
            if abs(a - c) <= rule["neighbor_tolerance"] and abs(b - (a + c) / 2) > rule["min_spike"]:
                add("isolated_spike", i, i + 1, [channel], {"threshold": rule["min_spike"]})
    zero_channels = config["zero_channels"]
    if any(c not in data.columns for c in zero_channels):
        raise DataError("Zero-run detector references an undeclared channel")
    start = None
    for i in range(n + 1):
        zero = i < n and bool(zero_channels) and all(
            data.columns[c][i] is not None and abs(data.columns[c][i]) <= config["zero_epsilon"]
            for c in zero_channels)
        if zero and start is None:
            start = i
        if not zero and start is not None:
            if i - start >= config["min_zero_rows"]:
                add("all_selected_channels_zero", start, i, zero_channels,
                    {"epsilon": config["zero_epsilon"], "scope": "selected_channels_only"})
            start = None
    return sorted(candidates, key=lambda e: (e["start_row"], e["stop_row"], e["candidate_id"]))


def group_candidates(candidates: list[dict], config: dict) -> list[list[dict]]:
    """Bound group span to avoid transitive chain-merging an entire experiment."""
    groups: list[list[dict]] = []
    for event in candidates:
        if groups:
            group = groups[-1]
            start = min(e["start_row"] for e in group)
            stop = max(e["stop_row"] for e in group)
            near = event["start_row"] <= stop + config["group_gap_rows"]
            bounded = max(stop, event["stop_row"]) - start <= config["max_group_span_rows"]
            if near and bounded:
                group.append(event)
                continue
        groups.append([event])
    return groups


def make_package(data: Telemetry, group: list[dict], config: dict) -> dict:
    n, w = len(data.times), config["context_rows"]
    a = min(e["start_row"] for e in group)
    b = max(e["stop_row"] for e in group)
    windows = {"context": {"start_row": max(0, a - w), "stop_row": min(n, b + w)}}
    if a > 0:
        windows["before"] = {"start_row": max(0, a - w), "stop_row": a}
    if b < n:
        windows["after"] = {"start_row": b, "stop_row": min(n, b + w)}
    priority = sorted({c for e in group for c in e["channels"]})
    channels = list(dict.fromkeys(priority + config["context_channels"]))[:config["max_channels"]]
    if any(c not in data.columns for c in channels):
        raise DataError("Fact package references an undeclared channel")
    package_id = "P_" + digest([data.sha256, data.source_hashes, group, windows, channels, config])[:16]
    facts, unavailable = [], []

    def record(query: dict, description: str, unit: str | None) -> None:
        try:
            value = evaluate(data, query)
        except DataError as error:
            unavailable.append({"description": description, "reason": str(error)})
            return
        facts.append({"fact_id": "F_" + digest([package_id, query])[:16], "description": description,
                      "query": query, "value": value, "unit": unit})

    for channel in channels:
        unit = data.entry["channels"][channel].get("unit")
        for name, window in windows.items():
            record({"op": "stat", "window": window, "channel": channel, "stat": "mean"},
                   f"Observed mean of {channel} in {name}; not a health classification.", unit)
        for stat in ("min", "max"):
            record({"op": "stat", "window": windows["context"], "channel": channel, "stat": stat},
                   f"Observed {stat} of {channel} in the context window.", unit)
        if "before" in windows and "after" in windows:
            record({"op": "delta", "channel": channel, "before": windows["before"], "after": windows["after"]},
                   f"After-minus-before mean difference of {channel}.", unit)
    record({"op": "duplicate_count", "window": windows["context"]},
           "Extra records with repeated timestamps in the context window; not necessarily identical rows.", "records")
    return {"schema_version": "0.1", "package_id": package_id,
            "experiment_id": data.entry["experiment_id"], "lineage_group": data.entry["lineage_group"],
            "split": data.entry["split"], "data_origin": data.entry["data_origin"],
            "source_sha256": data.sha256, "source_hashes": data.source_hashes,
            "candidates": group, "windows": windows,
            "channels": {c: data.entry["channels"][c] for c in channels},
            "facts": facts, "unavailable": unavailable,
            "context_observations": {c: [{"row": i, "value": values[i]}
                for i in range(windows["context"]["start_row"], windows["context"]["stop_row"])
                if i == windows["context"]["start_row"] or values[i] != values[i - 1]]
                for c, values in data.context.items()},
            "limitations": ["Detection rules are development heuristics, not fault ground truth.",
                            "Units are unknown unless explicitly supplied in the manifest.",
                            "No reliable command-dispatch timestamp or causal intervention is provided.",
                            "Temporal grouping is proximity-based and does not establish a shared cause."]}
