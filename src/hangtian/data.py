"""Explicit CSV loading, lineage checks and a closed numerical query language."""
from __future__ import annotations

import csv
import hashlib
import json
import math
import statistics
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


class DataError(ValueError):
    """An input violated a documented data contract."""


def digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def parse_time(value: str, entry: dict) -> float:
    if entry["time_kind"] == "seconds":
        result = float(value)
    else:
        fmt = entry.get("time_format")
        dt = datetime.strptime(value, fmt) if fmt else datetime.fromisoformat(value.replace("Z", "+00:00"))
        # Naive timestamps are interpreted on a naive local axis, never as UTC.
        origin = datetime(1970, 1, 1, tzinfo=dt.tzinfo)
        result = dt.timestamp() if dt.tzinfo is not None else (dt - origin).total_seconds()
    if not math.isfinite(result):
        raise DataError("Non-finite timestamp")
    return result


@dataclass
class Telemetry:
    entry: dict
    path: Path
    times: list[float]
    columns: dict[str, list[float | None]]
    context: dict[str, list[str]]
    sha256: str
    source_hashes: dict[str, str]

    def span(self, window: dict) -> range:
        a, b = window["start_row"], window["stop_row"]
        if type(a) is not int or type(b) is not int or not 0 <= a < b <= len(self.times):
            raise DataError("Invalid zero-based, half-open row window")
        return range(a, b)

    def values(self, channel: str, window: dict) -> list[float]:
        if channel not in self.columns:
            raise DataError("Channel not declared in the manifest")
        values = [self.columns[channel][i] for i in self.span(window)]
        if any(x is None for x in values):
            raise DataError("Missing values: this query does not impute or silently drop rows")
        return values  # type: ignore[return-value]


def load_csv(entry: dict, base: Path, max_rows: int = 250_000) -> Telemetry:
    path = (base / entry["telemetry_path"]).resolve()
    before_hash = file_hash(path)
    times: list[float] = []
    columns: dict[str, list[float | None]] = {c: [] for c in entry["channels"]}
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        required = set(columns) | {entry["time_column"]}
        if not required.issubset(reader.fieldnames or []):
            raise DataError("Missing declared CSV columns")
        if len(reader.fieldnames or []) != len(set(reader.fieldnames or [])):
            raise DataError("Duplicate CSV column names")
        for row in reader:
            if len(times) >= max_rows:
                raise DataError("max_rows exceeded; refusing to silently truncate an experiment")
            if None in row or any(v is None for v in row.values()):
                raise DataError("Malformed CSV row")
            times.append(parse_time(row[entry["time_column"]], entry))
            for channel in columns:
                token = row[channel].strip()
                value = None if token in {"", "NA", "NaN", "nan", "null"} else float(token)
                if value is not None and not math.isfinite(value):
                    raise DataError("Non-finite numeric value")
                columns[channel].append(value)
    if not times:
        raise DataError("Empty experiment")
    context: dict[str, list[str]] = {}
    hashes = {"telemetry": before_hash}
    for number, aux in enumerate(entry.get("auxiliary_files", [])):
        aux_path = (base / aux["path"]).resolve()
        hashes[f"auxiliary_{number}"] = file_hash(aux_path)
        # Labels are not loaded into the mining/model context in v0.1.
        if aux["role"] == "private_label":
            continue
        with aux_path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            if not (set(aux["fields"]) | {aux["time_column"]}).issubset(reader.fieldnames or []):
                raise DataError("Missing auxiliary columns")
            for c in aux["fields"]:
                if c in context or c in columns:
                    raise DataError("Colliding auxiliary field")
                context[c] = []
            count = 0
            for i, row in enumerate(reader):
                if i >= len(times) or parse_time(row[aux["time_column"]], entry) != times[i]:
                    raise DataError("Auxiliary alignment failed; timestamp-only joins are prohibited")
                for c in aux["fields"]:
                    context[c].append(row[c])
                count += 1
            if count != len(times):
                raise DataError("Auxiliary row count differs")
        if file_hash(aux_path) != hashes[f"auxiliary_{number}"]:
            raise DataError("Auxiliary file changed during loading")
    if file_hash(path) != before_hash:
        raise DataError("Telemetry changed during loading")
    return Telemetry(entry, path, times, columns, context, before_hash, hashes)


def check_lineage(entries: list[dict], base: Path) -> None:
    seen_ids: set[str] = set()
    groups: dict[str, str] = {}
    hashes: dict[str, tuple[str, str]] = {}
    for entry in entries:
        eid, group, split = entry["experiment_id"], entry["lineage_group"], entry["split"]
        if eid in seen_ids:
            raise DataError("Duplicate experiment ID")
        seen_ids.add(eid)
        if group in groups and groups[group] != split:
            raise DataError("A lineage group crosses dataset splits")
        groups[group] = split
        sha = file_hash((base / entry["telemetry_path"]).resolve())
        if sha in hashes and hashes[sha] != (group, split):
            raise DataError("Identical source bytes have inconsistent lineage or split")
        hashes[sha] = (group, split)


def evaluate(data: Telemetry, query: dict) -> float:
    """Execute only this allowlisted DSL; never eval/exec model-produced text."""
    op = query["op"]
    if op == "stat":
        values = data.values(query["channel"], query["window"])
        functions = {"mean": statistics.fmean, "median": statistics.median,
                     "min": min, "max": max, "count": len}
        if query["stat"] not in functions:
            raise DataError("Unknown statistic")
        return float(functions[query["stat"]](values))
    if op == "delta":
        a = evaluate(data, {"op": "stat", "window": query["before"], "channel": query["channel"], "stat": "mean"})
        b = evaluate(data, {"op": "stat", "window": query["after"], "channel": query["channel"], "stat": "mean"})
        return b - a
    if op == "duplicate_count":
        times = [data.times[i] for i in data.span(query["window"])]
        return float(len(times) - len(set(times)))
    if op == "first_crossing":
        indices = list(data.span(query["window"]))
        if any(data.times[b] <= data.times[a] for a, b in zip(indices, indices[1:])):
            raise DataError("A temporal metric requires a strictly increasing time axis")
        values = data.values(query["channel"], query["window"])
        for i, value in zip(indices, values):
            hit = value >= query["threshold"] if query["direction"] == "above" else value <= query["threshold"]
            if hit:
                return data.times[i] - data.times[indices[0]]
        raise DataError("Threshold not reached")
    raise DataError("Unsupported computation")
