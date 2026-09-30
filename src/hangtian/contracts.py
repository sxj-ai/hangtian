"""Closed JSON contracts and deterministic cross-reference gates."""
from __future__ import annotations

import json
import math
from copy import deepcopy
from pathlib import Path
from jsonschema import Draft202012Validator
from .data import DataError, Telemetry, digest, evaluate


def obj(properties: dict, optional: tuple[str, ...] = ()) -> dict:
    return {"type": "object", "properties": properties,
            "required": [k for k in properties if k not in optional], "additionalProperties": False}


def arr(items: dict, minimum: int = 0, maximum: int = 200) -> dict:
    return {"type": "array", "items": items, "minItems": minimum, "maxItems": maximum}


def enum(*values: str) -> dict:
    return {"type": "string", "enum": list(values)}


TEXT = {"type": "string", "minLength": 1, "maxLength": 6000}
IDENTIFIER = {"type": "string", "pattern": "^[A-Za-z][A-Za-z0-9_-]{0,79}$"}
FACT_IDS = arr(IDENTIFIER)
WINDOW = obj({"start_row": {"type": "integer", "minimum": 0},
              "stop_row": {"type": "integer", "minimum": 1}})
CHANNEL = obj({"unit": {"type": ["string", "null"]}, "component": TEXT})
QUERY = {"oneOf": [
    obj({"op": {"const": "stat"}, "channel": TEXT, "window": WINDOW,
         "stat": enum("mean", "median", "min", "max", "count")}),
    obj({"op": {"const": "delta"}, "channel": TEXT, "before": WINDOW, "after": WINDOW}),
    obj({"op": {"const": "duplicate_count"}, "window": WINDOW}),
    obj({"op": {"const": "first_crossing"}, "channel": TEXT, "window": WINDOW,
         "threshold": {"type": "number"}, "direction": enum("above", "below")})]}
TASK_TYPES = ("state_comparison", "temporal_localization", "differential_investigation",
              "evidence_sufficiency", "data_quality_investigation", "integrated_investigation")
AUX = obj({"path": TEXT, "time_column": TEXT, "fields": arr(TEXT, 1),
           "role": enum("context", "private_label")})
EXPERIMENT = obj({"experiment_id": IDENTIFIER, "lineage_group": IDENTIFIER,
                  "split": enum("development", "train", "validation", "test"),
                  "data_origin": enum("synthetic", "real"), "telemetry_path": TEXT,
                  "time_column": TEXT, "time_kind": enum("seconds", "datetime"),
                  "time_format": TEXT, "channels": {"type": "object", "minProperties": 1,
                    "additionalProperties": CHANNEL}, "auxiliary_files": arr(AUX)}, ("time_format",))
CASE = obj({"package_id": IDENTIFIER, "decision": enum("accept", "defer", "reject"),
            "summary": TEXT, "fact_ids": FACT_IDS,
            "hypotheses": arr(obj({"description": TEXT, "supporting_fact_ids": FACT_IDS,
                                    "contradicting_fact_ids": FACT_IDS, "missing_evidence": arr(TEXT)})),
            "limitations": arr(TEXT, 1), "requested_context": arr(TEXT)})
TASK = obj({"local_id": IDENTIFIER, "task_type": enum(*TASK_TYPES), "title": TEXT,
            "prompt": TEXT, "observable_goal": TEXT, "fact_ids": arr(IDENTIFIER, 1),
            "numeric_checks": arr(obj({"answer_key": IDENTIFIER, "fact_id": IDENTIFIER}), 0, 12),
            "evidence_requirements": arr(TEXT, 1), "hypotheses_to_compare": arr(TEXT),
            "limitations_to_address": arr(TEXT, 1),
            "semantic_rubric": arr(obj({"criterion": TEXT, "supporting_fact_ids": FACT_IDS}), 1),
            "investigation_decisions": arr(TEXT), "distinctness_rationale": TEXT,
            "difficulty": enum("basic", "guided_investigation")})
REVIEW = obj({"local_id": IDENTIFIER, "decision": enum("accept", "basic_only", "revise", "reject"),
              "scores": obj({k: {"type": "integer", "minimum": 0, "maximum": 3}
                             for k in ("grounding", "data_dependence", "distinctness", "investigation_value")}),
              "issues": arr(obj({"severity": enum("blocking", "warning"),
                                  "code": enum("UNSUPPORTED_CLAIM", "ANSWER_LEAKAGE", "DUPLICATE_TASK",
                                    "MISSING_DEFINITION", "LOW_INVESTIGATION_VALUE", "UNAVAILABLE_TOOL",
                                    "RUBRIC_MISMATCH", "QUALITY_CONFOUND", "OTHER"),
                                  "message": TEXT, "fact_ids": FACT_IDS})), "rationale": TEXT})
SCHEMAS = {
    "manifest": obj({"schema_version": {"const": "0.1"}, "experiments": arr(EXPERIMENT, 1)}),
    "case": CASE,
    "tasks": obj({"package_id": IDENTIFIER, "tasks": arr(TASK, 0, 3)}),
    "critique": obj({"package_id": IDENTIFIER, "reviews": arr(REVIEW, 0, 3)}),
    "query": QUERY,
}


POS = {"type": "integer", "minimum": 1}
NONNEG = {"type": "number", "minimum": 0}
MODEL_SETTINGS = obj({"base_url": TEXT, "api_key_env": IDENTIFIER, "model": TEXT,
                      "max_tokens": {"type": "integer", "minimum": 256, "maximum": 32768},
                      "temperature": {"type": "number", "minimum": 0, "maximum": 2}})
SCHEMAS["config"] = obj({
    "schema_version": {"const": "0.1"}, "max_rows": POS,
    "max_cases": {"type": "integer", "minimum": 1, "maximum": 1000},
    "max_revisions": {"type": "integer", "minimum": 0, "maximum": 3},
    "task_language": TEXT, "max_api_calls": POS,
    "transport_retries": {"type": "integer", "minimum": 0, "maximum": 3},
    "timeout_seconds": POS, "max_input_bytes": POS, "max_response_bytes": POS,
    "models": obj({r: MODEL_SETTINGS for r in ("case_curator", "task_generator", "task_critic")}),
    "mining": obj({"window_rows": POS, "noise_multiplier": NONNEG, "group_gap_rows": {"type": "integer", "minimum": 0},
        "max_group_span_rows": POS, "context_rows": POS, "max_channels": POS,
        "context_channels": arr(TEXT, 1), "zero_channels": arr(TEXT), "zero_epsilon": NONNEG,
        "min_zero_rows": POS, "channels": {"type": "object", "additionalProperties": obj({
            "min_step": NONNEG, "min_spike": NONNEG, "neighbor_tolerance": NONNEG})}})
})


def schema(kind: str) -> dict:
    return {"$schema": "https://json-schema.org/draft/2020-12/schema", **deepcopy(SCHEMAS[kind])}


def validate(kind: str, value: dict) -> None:
    errors = sorted(Draft202012Validator(schema(kind)).iter_errors(value), key=lambda e: str(e.path))
    if errors:
        error = errors[0]
        # Do not echo arbitrarily long model strings or input values into errors.
        raise DataError(f"{kind}: schema violation at {'/'.join(map(str, error.path)) or '/'} ({error.validator})")


def fact_map(package: dict) -> dict[str, dict]:
    return {f["fact_id"]: f for f in package["facts"]}


def referenced_ids(value: object) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for k, v in value.items():
            if k.endswith("fact_ids"):
                found.update(v)
            elif k == "fact_id":
                found.add(v)
            else:
                found.update(referenced_ids(v))
    elif isinstance(value, list):
        for v in value:
            found.update(referenced_ids(v))
    return found


def check_references(value: dict, package: dict) -> None:
    if value["package_id"] != package["package_id"]:
        raise DataError("Package ID mismatch")
    if referenced_ids(value) - set(fact_map(package)):
        raise DataError("Unknown or invented fact reference")


def verify_case(value: dict, package: dict) -> None:
    validate("case", value)
    check_references(value, package)
    if value["decision"] == "accept" and not value["fact_ids"]:
        raise DataError("Accepted case has no grounded facts")


def recompute(package: dict, fresh: Telemetry) -> dict[str, float]:
    if fresh.sha256 != package["source_sha256"] or fresh.source_hashes != package["source_hashes"]:
        raise DataError("Source snapshot changed")
    expected = {}
    for fact in package["facts"]:
        validate("query", fact["query"])
        value = evaluate(fresh, fact["query"])
        if not math.isclose(value, fact["value"], abs_tol=1e-8, rel_tol=1e-8):
            raise DataError("Fact recomputation mismatch")
        expected[fact["fact_id"]] = value
    return expected


def verify_tasks(value: dict, package: dict) -> None:
    validate("tasks", value)
    check_references(value, package)
    keys, signatures = set(), set()
    for task in value["tasks"]:
        if task["local_id"] in keys:
            raise DataError("Duplicate task local ID")
        keys.add(task["local_id"])
        signature = digest([task["task_type"], sorted(task["fact_ids"]),
                            sorted(c["fact_id"] for c in task["numeric_checks"])])
        if signature in signatures:
            raise DataError("Duplicate task structure; wording changes are not new tasks")
        signatures.add(signature)
        answer_keys = [c["answer_key"] for c in task["numeric_checks"]]
        if len(answer_keys) != len(set(answer_keys)):
            raise DataError("Duplicate answer key")
        if task["difficulty"] == "guided_investigation" and not task["investigation_decisions"]:
            raise DataError("An investigation requires decision opportunities, not a claimed call count")


def verify_critique(value: dict, tasks: dict, package: dict) -> None:
    validate("critique", value)
    check_references(value, package)
    ids = [x["local_id"] for x in value["reviews"]]
    if len(ids) != len(set(ids)) or set(ids) != {t["local_id"] for t in tasks["tasks"]}:
        raise DataError("Critique must cover each task exactly once")
    for review in value["reviews"]:
        if review["decision"] in {"accept", "basic_only"} and any(x["severity"] == "blocking" for x in review["issues"]):
            raise DataError("A blocking issue cannot be overridden by an accept verdict")


def export_task(task: dict, package: dict, expected: dict, mode: str) -> tuple[dict, dict]:
    """Whitelist export: fact values, case interpretations and source paths stay private."""
    facts = fact_map(package)
    tid = "T_" + digest([package["package_id"], task])[:20]
    public = {k: task[k] for k in ("title", "prompt", "task_type", "observable_goal", "difficulty")}
    public.update({"task_id": tid, "case_id": "C_" + package["package_id"][2:],
                   "status": "fixture_only" if mode == "mock" else "critic_pass_pending_solver",
                   "data_origin": package["data_origin"], "experiment_id": package["experiment_id"],
                   "permitted_window": package["windows"]["context"], "channels": package["channels"],
                   "tools": ["inspect_channels", "read_window", "summarize_window", "compare_windows",
                             "check_time_axis", "first_crossing", "submit_report"],
                   "measurement_requirements": [{"answer_key": c["answer_key"],
                       "definition": facts[c["fact_id"]]["query"], "unit": facts[c["fact_id"]]["unit"]}
                       for c in task["numeric_checks"]],
                   "response_requirements": ["Return requested measurements with record-based evidence.",
                     "Report conclusions, alternatives and unresolved uncertainties."]})
    private = {"task_id": tid, "lineage_group": package["lineage_group"], "split": package["split"],
               "source_hashes": package["source_hashes"], "specification": task,
               "expected_measurements": {c["answer_key"]: expected[c["fact_id"]] for c in task["numeric_checks"]},
               "tolerance": {"atol": 1e-8, "rtol": 1e-8}, "semantic_review_required": True}
    return public, private


def export_schemas(directory: Path) -> None:
    from .data import write_json
    for kind in SCHEMAS:
        write_json(directory / f"{kind}.schema.json", schema(kind))
