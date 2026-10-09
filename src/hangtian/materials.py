"""Audited recipes -> multi-record material, recomputable facts and bounded tools.

Recipes are trusted researcher inputs. Model output cannot add files or executable code.
Raw telemetry remains in acquisition order; context is aligned by row AND timestamp.
"""
from __future__ import annotations

import csv
import json
import math
import statistics
from pathlib import Path

from .contracts import validate
from .data import DataError, digest, file_hash, parse_time, write_json


VERSION = "material-engine-0.3.0"


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_records(recipe: dict, base: Path) -> tuple[dict, list[dict]]:
    records, provenance = {}, []
    for spec in recipe["records"]:
        rid = spec["record_id"]
        if rid in records:
            raise DataError("Duplicate record ID")
        a, b = spec["source_rows"]
        if type(a) is not int or type(b) is not int or not 0 <= a < b:
            raise DataError("Invalid source row window")
        path = (base / spec["telemetry_path"]).resolve()
        aux = (base / spec["context_path"]).resolve()
        hashes = {"telemetry": file_hash(path), "context": file_hash(aux)}
        if hashes != spec["source_hashes"]:
            raise DataError("Source bytes differ from audited recipe")
        with path.open(encoding="utf-8-sig", newline="") as f, aux.open(encoding="utf-8-sig", newline="") as g:
            tele, ctx = csv.DictReader(f), csv.DictReader(g)
            channels = {c: [] for c in recipe["channels"]}
            if not set(channels).issubset(set(tele.fieldnames or []) | set(ctx.fieldnames or [])):
                raise DataError("Missing declared channels")
            times, absolute = [], []
            for i, row in enumerate(tele):
                other = next(ctx, None)
                if other is None or row["Time"] != other["Time"]:
                    raise DataError("Context row/timestamp alignment failed")
                if a <= i < b:
                    absolute.append(parse_time(row["Time"], {"time_kind": "datetime"}))
                    merged = {**row, **{k: v for k, v in other.items() if k != "Time"}}
                    for c in channels:
                        v = float(merged[c])
                        if not math.isfinite(v):
                            raise DataError("Nonfinite value; no silent cleaning")
                        channels[c].append(v)
            if next(ctx, None) is not None or len(absolute) != b - a:
                raise DataError("Source/context length mismatch or incomplete selection")
            times = [v - absolute[0] for v in absolute]
        if {"telemetry": file_hash(path), "context": file_hash(aux)} != hashes:
            raise DataError("Source changed during reading")
        if "regions" in spec:
            regions = {"full_record": [a, b], **spec["regions"]}
            for name, bounds in regions.items():
                if len(bounds) != 2 or any(type(i) is not int for i in bounds) or not a <= bounds[0] < bounds[1] <= b:
                    raise DataError("Declared region outside the selected source rows")
                validate("material_query", {"record_id": rid, "op": "quality", "region": name, "slice": "all"})
            if regions["full_record"] != [a, b]:
                raise DataError("full_record must cover the complete selected record")
        else:
            low = [i for i, v in enumerate(channels["Irradiation"]) if v == recipe["low_irradiation_value"]]
            if not low or low != list(range(low[0], low[-1] + 1)):
                raise DataError("Expected one contiguous low-irradiation phase per record")
            regions = {"full_cycle": [a, b], "low_irr": [a + low[0], a + low[-1] + 1]}
        records[rid] = {"record_id": rid, "series_id": spec["series_id"],
            "sequence_index": spec["sequence_index"], "row_origin": a,
            "time_s": times, "channels": channels,
            "regions": regions}
        provenance.append({**spec, "selected_rows": b - a,
            "transformation": "Exact ordered rows; numeric parsing only; time relative to first selected row."})
    return records, provenance


def quality(record: dict, a: int, b: int) -> dict:
    times = record["time_s"][a:b]
    groups = {}
    for i in range(a, b):
        groups.setdefault(record["time_s"][i], []).append(i)
    conflict_channels, conflicts = set(), 0
    for ids in groups.values():
        changed = {c for c, values in record["channels"].items()
                   if any(values[i] != values[ids[0]] for i in ids[1:])}
        if changed:
            conflicts += 1
            conflict_channels.update(changed)
    return {"rows": b - a, "duplicate_extra_rows": len(times) - len(set(times)),
        "conflicting_timestamp_groups": conflicts,
        "conflict_channel_count": len(conflict_channels), "conflict_channels": sorted(conflict_channels),
        "time_reversals": sum(y < x for x, y in zip(times, times[1:])),
        "gaps_gt_1s": sum(y - x > 1 for x, y in zip(times, times[1:])),
        "max_gap_s": max((y - x for x, y in zip(times, times[1:])), default=0),
        "elapsed_span_s": times[-1] - times[0]}


def sustained(record: dict, a: int, b: int, channel: str, threshold: float, count: int, direction="above"):
    times = record["time_s"]
    if any(times[i] <= times[i-1] for i in range(a + 1, b)):
        raise DataError("Temporal onset requires strictly increasing timestamps in this region")
    run = 0
    for i in range(a, b):
        value = record["channels"][channel][i]
        hit = value > threshold if direction == "above" else value < threshold
        run = run + 1 if hit else 0
        if run >= count:
            return i - count + 1
    return None


def execute(records: dict, query: dict) -> dict:
    validate("material_query", query)
    if query["record_id"] not in records:
        raise DataError("Record outside allowed material")
    r = records[query["record_id"]]
    if query["region"] not in r["regions"]:
        raise DataError("Undeclared region")
    origin = r["row_origin"]
    a, b = [i - origin for i in r["regions"][query["region"]]]
    base_a = a
    selection = query["slice"]
    if selection == "last60s":
        if any(r["time_s"][i] < r["time_s"][i-1] for i in range(a+1,b)):
            raise DataError("Elapsed-time slicing requires a nondecreasing time axis")
        # Inclusive lower timestamp bound: elapsed-time slice, not a fixed row count.
        a = next(i for i in range(a, b) if r["time_s"][i] >= r["time_s"][b-1] - 59)
    elif selection in {"before_recovery30", "after_recovery30"}:
        onset = sustained(r, a, b, "P_SA", 5, 20)
        if onset is None:
            raise DataError("No sustained recovery; requested anchor window unavailable")
        a, b = (onset - 30, onset) if selection == "before_recovery30" else (onset, onset + 30)
        lo, hi = [i - origin for i in r["regions"][query["region"]]]
        if not lo <= a < b <= hi:
            raise DataError("Anchor window exceeds requested region")
    result = {"source_rows": [origin + a, origin + b], "quality": quality(r, a, b)}
    op = query["op"]
    if op == "quality":
        if set(query) - {"metric"} != {"record_id", "op", "region", "slice"}:
            raise DataError("Unexpected quality query fields")
        result["value"] = result["quality"][query.get("metric", "duplicate_extra_rows")]
    elif op == "longest_zero_run":
        if set(query) != {"record_id", "op", "region", "slice", "channels"}:
            raise DataError("Invalid all-selected-channel zero-run query")
        if len(set(query["channels"])) != len(query["channels"]) or not set(query["channels"]).issubset(r["channels"]):
            raise DataError("Invalid zero-run channel set")
        longest, start = None, None
        for i in range(a, b+1):
            hit = i < b and all(r["channels"][c][i] == 0 for c in query["channels"])
            if hit and start is None:
                start = i
            if not hit and start is not None:
                if longest is None or i-start > longest[1]-longest[0]:
                    longest = (start, i)
                start = None
        result["value"] = 0 if longest is None else longest[1]-longest[0]
        result["run_source_rows"] = None if longest is None else [origin+longest[0], origin+longest[1]]
        result["run_start_offset_s"] = None if longest is None else r["time_s"][longest[0]]-r["time_s"][base_a]
        result["meaning"] = "Longest contiguous acquisition-order run with every selected channel exactly zero. Row count, not seconds. Earliest run wins ties."
    else:
        channel = query.get("channel")
        if channel not in r["channels"]:
            raise DataError("Undeclared channel")
        if op == "stat":
            if set(query) != {"record_id", "op", "region", "slice", "channel", "stat"}:
                raise DataError("Invalid statistic query")
            functions = {"median": statistics.median, "mean": statistics.fmean,
                         "min": min, "max": max, "count": len}
            result["value"] = float(functions[query["stat"]](r["channels"][channel][a:b]))
        else:
            if selection != "all" or set(query) - {"direction"} != {"record_id", "op", "region", "slice", "channel", "threshold", "min_records"}:
                raise DataError("Sustained onset requires the whole named region and explicit definition")
            onset = sustained(r, a, b, channel, query["threshold"], query["min_records"], query.get("direction", "above"))
            result["value"] = None if onset is None else r["time_s"][onset] - r["time_s"][base_a]
            result["onset_source_row"] = None if onset is None else origin + onset
            result["meaning"] = "Seconds since first region record; null means not observed inside this region. Consecutive records are not seconds."
    return result


class MaterialTools:
    def __init__(self, records: dict, allowed_records: list[str]):
        if not set(allowed_records).issubset(records):
            raise DataError("Unknown allowed record")
        self.records = {k: records[k] for k in allowed_records}
        self.observations: list[dict] = []

    def call(self, query: dict) -> dict:
        result = execute(self.records, query)
        obs = {"query": query, "result": result}
        obs["observation_id"] = "O_" + digest(obs)[:20]
        self.observations.append(obs)
        return obs


def build_material(recipe_path: Path, out: Path) -> tuple[dict, dict]:
    recipe = read_json(recipe_path)
    records, provenance = load_records(recipe, recipe_path.parent)
    facts = []
    if len({f["fact_id"] for f in recipe["facts"]}) != len(recipe["facts"]):
        raise DataError("Duplicate fact ID")
    for spec in recipe["facts"]:
        result = execute(records, spec["query"])
        facts.append({**spec, "result": result})
    known = {f["fact_id"] for f in facts}
    for interpretation in recipe["interpretations"]:
        if not set(interpretation["fact_ids"]).issubset(known):
            raise DataError("Unknown interpretation evidence")
    catalog = [{k: r[k] for k in ("record_id", "series_id", "sequence_index", "regions")} |
               {"quality": quality(r, 0, len(r["time_s"]))} for r in records.values()]
    material = {"schema_version": "0.2", "material_id": recipe["material_id"],
        "engine_version": VERSION, "recipe_sha256": digest(recipe),
        "title": recipe["title"], "data_origin": recipe["data_origin"],
        "public_background": recipe["public_background"], "channels": recipe["channels"],
        "record_catalog": catalog, "facts": facts, "interpretations": recipe["interpretations"],
        "task_slots": recipe["task_slots"], "limitations": recipe["limitations"],
        "provenance": provenance, "forbidden_public_strings": recipe["forbidden_public_strings"],
        "selection_rationale": recipe["selection_rationale"],
        "evidence_sources": recipe["evidence_sources"]}
    if recipe.get("require_model_written_interpretations"):
        material["require_model_written_interpretations"] = True
    if recipe.get("generation_feedback"):
        material["generation_feedback"] = recipe["generation_feedback"]
    write_json(out / "private/material.json", material)
    write_json(out / "private/records.json", records)
    write_json(out / "public/data_catalog.json", {"material_id": material["material_id"],
        "records": [{k: v for k, v in r.items() if k != "quality"} for r in catalog],
        "channels": material["channels"], "background": material["public_background"]})
    # The query data are solver-visible; original filenames/labels/provenance are not.
    write_json(out / "public/records.json", records)
    return material, records


def authoring_view(material: dict) -> dict:
    return {k: v for k, v in material.items() if k not in {
        "provenance", "forbidden_public_strings", "recipe_sha256", "evidence_sources", "generation_feedback"}}


def generation_view(material: dict) -> dict:
    """Question-design contract: exact scope and hypotheses, no answer values."""
    facts = {f['fact_id']: f for f in material['facts']}
    rules = {r['interpretation_id']: r for r in material['interpretations']}
    catalog = [{k: v for k, v in r.items() if k != 'quality'} for r in material['record_catalog']]
    groups = {}
    for r in catalog:
        if 'series_id' in r:
            groups.setdefault(r['series_id'], []).append(r['record_id'])
    slots = []
    for slot in material['task_slots']:
        slots.append({**{k:v for k,v in slot.items() if k != 'focus'}, 'measurements': [
            {'measurement_id': i, 'query': facts[i]['query'], 'unit': facts[i]['unit']} for i in slot['measurement_ids']],
            'interpretations': [{'interpretation_id': i, 'statement': rules[i]['statement']}
                               for i in slot['interpretation_ids']]})
    return {'material_id': material['material_id'], 'public_background': material['public_background'],
        'channels': material['channels'], 'record_catalog': catalog, 'source_groups': groups,
        'task_slots': slots, 'require_model_written_interpretations': material.get('require_model_written_interpretations', False),
        'design_mode': 'Guided evidence analysis; each slot objective is defined by its supplied propositions. Their truth values are unknown to the generator.'}


def verify_proposal(proposal: dict, material: dict) -> None:
    validate("material_tasks", proposal)
    if proposal["material_id"] != material["material_id"]:
        raise DataError("Wrong material ID")
    slots = {s["slot_id"]: s for s in material["task_slots"]}
    if set(t["slot_id"] for t in proposal["tasks"]) != set(slots) or len(proposal["tasks"]) != len(slots):
        raise DataError("Each research slot must produce exactly one distinct task")
    if len({t["task_id"] for t in proposal["tasks"]}) != len(slots):
        raise DataError("Duplicate task ID")
    facts = {f["fact_id"]: f for f in material["facts"]}
    interpretations = {r["interpretation_id"]: r for r in material["interpretations"]}
    for task in proposal["tasks"]:
        slot = slots[task["slot_id"]]
        if slot.get("target_task_id") and task["task_id"] != slot["target_task_id"]:
            raise DataError("Task ID must equal the slot target_task_id")
        for key in ("measurement_ids", "interpretation_ids", "required_record_ids"):
            if len(task[key]) != len(set(task[key])):
                raise DataError("Duplicate task reference")
        if set(task["measurement_ids"]) != set(slot["measurement_ids"]) or set(task["interpretation_ids"]) != set(slot["interpretation_ids"]):
            raise DataError("Task must retain the slot's complete audited evidence and interpretation coverage")
        records = {facts[i]["query"]["record_id"] for i in task["measurement_ids"]}
        if set(task["required_record_ids"]) != records:
            raise DataError("Task record scope does not match its measurements")
        for item in task["interpretation_ids"]:
            if not set(interpretations[item]["fact_ids"]).issubset(task["measurement_ids"]):
                raise DataError("Interpretation evidence is not accessible to solver")
        statements = task.get("interpretation_statements", [])
        if material.get("require_model_written_interpretations") or statements:
            ids = [s["interpretation_id"] for s in statements]
            if len(ids) != len(set(ids)) or set(ids) != set(task["interpretation_ids"]):
                raise DataError("Model-written statements must cover every interpretation exactly once")
        leak_scan(public_task(task, material), material)


def leak_scan(value: dict, material: dict) -> None:
    text = json.dumps(value, ensure_ascii=False).casefold()
    banned = material["forbidden_public_strings"] + ["expected_verdict", "expected_value", "source_hashes", "telemetry_path", "anomalylabel"]
    if any(token.casefold() in text for token in banned if token):
        raise DataError("Public artifact contains prohibited private text")


def public_task(task: dict, material: dict) -> dict:
    facts = {f["fact_id"]: f for f in material["facts"]}
    interpretations = {r["interpretation_id"]: r for r in material["interpretations"]}
    statements = {s["interpretation_id"]: s["statement"] for s in task.get("interpretation_statements", [])}
    return {k: task[k] for k in ("task_id", "slot_id", "title", "prompt", "required_record_ids")} | {
        "material_id": material["material_id"], "background": material["public_background"],
        "records": [{k: v for k, v in r.items() if k != "quality"}
                    for r in material["record_catalog"] if r["record_id"] in task["required_record_ids"]],
        "channels": material["channels"],
        "measurements": [{"measurement_id": i, "definition": facts[i]["definition"], "query": facts[i]["query"], "unit": facts[i]["unit"]} for i in task["measurement_ids"]],
        "interpretations": [{"interpretation_id": i, "statement": statements.get(i, interpretations[i]["statement"])} for i in task["interpretation_ids"]],
        "response_rule": "Compute every measurement with tools. For every statement choose supported/refuted/insufficient and cite tool observation IDs. Explain limitations. A submission is not a correctness verdict."}
