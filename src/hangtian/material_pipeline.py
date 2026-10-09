"""Resumable, stage-separated pilot/batch execution. No model verdict overrides code."""
from __future__ import annotations

import json
import math
import platform
import traceback
from copy import deepcopy
from pathlib import Path

from .contracts import validate
from .data import DataError, digest, file_hash, write_json
from .materials import (VERSION, MaterialTools, authoring_view, generation_view, build_material,
                        execute, leak_scan, public_task, read_json, verify_proposal)


def checked_stage(out: Path, name: str, inputs: dict, compute):
    path = out / "private" / "stages" / (name + ".json")
    fingerprint = digest(inputs)
    if path.exists():
        cached = read_json(path)
        if cached["input_sha256"] != fingerprint or digest(cached["result"]) != cached["result_sha256"]:
            raise DataError("Stage cache changed; use a new output directory")
        return cached["result"]
    result = compute()
    write_json(path, {"input_sha256": fingerprint, "result_sha256": digest(result), "result": result})
    return result


def task_review_gate(review: dict, proposal: dict):
    validate("material_review", review)
    ids = [t["task_id"] for t in proposal["tasks"]]
    reviews = review["reviews"]
    if len(reviews) != len(ids) or set(r["task_id"] for r in reviews) != set(ids):
        raise DataError("Incomplete/duplicate task reviews")
    if any(r["decision"] != "accept" or r["leakage"] for r in reviews):
        raise DataError("Task critic did not accept all tasks without leakage")


def generate(material: dict, model, config: dict, out: Path):
    feedback = material.get("generation_feedback", [])
    for revision in range(config["max_revisions"] + 1):
        proposal = model.call("material_generator", {"material": generation_view(material),
            "language": "Chinese", "feedback": feedback}, "material_tasks")
        write_json(out / f"private/generation_attempt_{revision}.json", proposal)
        try:
            verify_proposal(proposal, material)
            exported = [public_task(t, material) for t in proposal["tasks"]]
            if config.get("review_mode", "api") == "assistant":
                return {"proposal": proposal, "review": None, "public_tasks": exported,
                        "status": "pending_assistant_review", "authorship": "remote_api" if model.mode == "remote" else "fixture"}
            review = model.call("material_critic", {"material": authoring_view(material),
                "proposal": proposal, "public_tasks": exported}, "material_review")
            write_json(out / f"private/task_review_{revision}.json", review)
            task_review_gate(review, proposal)
            return {"proposal": proposal, "review": review, "public_tasks": exported}
        except DataError as error:
            feedback = [{"code_gate": str(error)}]
            if "review" in locals():
                feedback.append({"critic_review": review})
            if revision == config["max_revisions"]:
                raise
    raise DataError("No accepted proposal")


def solve(task: dict, records: dict, model, config: dict, out: Path):
    tool = MaterialTools(records, task["required_record_ids"])
    history, answer, errors = [], None, []
    # Deliberately no private material, fact values, labels, reference answer or critic output.
    for index in range(config["max_solver_steps"]):
        payload = {"task": task, "observations": tool.observations,
                   "tool_errors": errors, "steps_remaining": config["max_solver_steps"] - index}
        step = model.call("material_solver", payload, "solver_step")
        history.append(step)
        write_json(out / "private" / f"trajectory_{task['task_id']}.json",
                   {"task_id": task["task_id"], "steps": history, "observations": tool.observations, "errors": errors})
        try:
            validate("solver_step", step)
            if step["action"] == "submit":
                answer = step["answer"]
                break
            for query in step["queries"]:
                try:
                    tool.call(query)
                except (DataError, KeyError) as error:
                    errors.append({"query": query, "error": str(error)})
        except DataError as error:
            errors.append({"error": str(error)})
    return {"task_id": task["task_id"], "steps": history, "observations": tool.observations,
            "tool_errors": errors, "answer": answer,
            "status": "submitted" if answer is not None else "step_budget_exhausted"}


def equal_number(actual, expected, tolerance=1e-6):
    if expected is None:
        return actual is None
    return type(actual) in (int, float) and math.isfinite(actual) and math.isclose(actual, expected, rel_tol=0, abs_tol=tolerance)


def validate_answer(task: dict, material: dict, records: dict, trajectory: dict):
    facts = {f["fact_id"]: f for f in material["facts"]}
    rules = {r["interpretation_id"]: r for r in material["interpretations"]}
    issues, checks = [], []
    answer = trajectory["answer"]
    if answer is None:
        return {"hard_pass": False, "checks": [], "issues": ["No submitted answer"]}
    try:
        validate("pilot_answer", answer)
    except DataError as error:
        return {"hard_pass": False, "checks": [], "issues": [str(error)]}
    observed = {o["observation_id"]: o for o in trajectory["observations"]}
    # Replay every observation from raw material; forged/corrupt trajectories cannot earn credit.
    for oid, obs in observed.items():
        if obs["query"]["record_id"] not in task["required_record_ids"]:
            issues.append("Observation outside task scope")
            continue
        recomputed = execute(records, obs["query"])
        if recomputed != obs["result"] or oid != "O_" + digest({"query": obs["query"], "result": recomputed})[:20]:
            issues.append("Observation replay mismatch")
    measurements = {a["measurement_id"]: a for a in answer["measurements"]}
    if len(measurements) != len(answer["measurements"]) or set(measurements) != set(task["measurement_ids"]):
        issues.append("Measurement ID coverage mismatch")
    for fid in task["measurement_ids"]:
        spec = facts[fid]
        expected_result = execute(records, spec["query"])
        if expected_result != spec["result"]:
            issues.append("Authoring fact failed recomputation")
        item = measurements.get(fid, {})
        obs = observed.get(item.get("observation_id"), {})
        passed = ("value" in item and equal_number(item["value"], expected_result["value"])
                  and obs.get("query") == spec["query"] and obs.get("result") == expected_result)
        checks.append({"kind": "measurement", "id": fid, "pass": passed,
            "expected": expected_result["value"], "actual": item.get("value"), "tolerance": 1e-6})
    interpretations = {a["interpretation_id"]: a for a in answer["interpretations"]}
    if len(interpretations) != len(answer["interpretations"]) or set(interpretations) != set(task["interpretation_ids"]):
        issues.append("Interpretation ID coverage mismatch")
    for iid in task["interpretation_ids"]:
        rule, item = rules[iid], interpretations.get(iid, {})
        citations = item.get("observation_ids", [])
        cited_queries = {digest(observed[o]["query"]) for o in citations if o in observed}
        needed = {digest(facts[f]["query"]) for f in rule["fact_ids"]}
        passed = (item.get("verdict") == rule["expected_verdict"] and needed.issubset(cited_queries)
                  and all(o in observed for o in citations))
        checks.append({"kind": "interpretation_and_evidence", "id": iid, "pass": passed,
            "expected": rule["expected_verdict"], "actual": item.get("verdict"),
            "reference_basis": rule["basis_type"]})
    return {"hard_pass": not issues and all(c["pass"] for c in checks), "checks": checks, "issues": issues}


def run_case(recipe_path: Path, config: dict, model, out: Path, project_root: Path, stage: str):
    recipe = read_json(recipe_path)
    prompt_hashes = {r: file_hash(project_root / "prompts" / (r + ".md")) for r in config["models"]}
    # Include implementation bytes, not only a manually bumped version, in resumability identity.
    code_hashes = {p.name: file_hash(p) for p in Path(__file__).parent.glob("*.py")}
    identity = {"recipe": digest(recipe), "config": digest(config), "engine": VERSION,
                "code": code_hashes, "prompts": prompt_hashes, "backend": model.mode}
    marker = out / "private/run_identity.json"
    if marker.exists() and read_json(marker) != identity:
        raise DataError("Run inputs/code/prompts changed; choose a new output directory")
    write_json(marker, identity)
    write_json(out / "private/runtime.json", {"hostname": platform.node(), "python": platform.python_version(),
        "platform": platform.platform(), "recipe_path": str(recipe_path.resolve())})
    # Re-read and hash raw files even on resume. Cached answers cannot bless changed data.
    material, records = build_material(recipe_path, out)
    summary = {"material_id": material["material_id"], "status": "materials_ready",
        "records": len(records), "source_lineages": len({p["series_id"] for p in material["provenance"]}),
        "fact_count": len(material["facts"]), "tasks_generated": 0, "trajectories": 0, "pilot_passed": 0,
        "mode": model.mode, "data_origin": material["data_origin"]}
    if stage == "materials":
        write_json(out / "summary.json", summary)
        return summary
    generated = checked_stage(out, "generate", identity, lambda: generate(material, model, config, out))
    verify_proposal(generated["proposal"], material)
    if config.get("review_mode", "api") == "assistant":
        write_json(out / "private/generated_candidate.json", generated)
        write_json(out / "candidate_tasks.json", generated["public_tasks"])
        summary.update(status="api_generated_pending_assistant_review", tasks_generated=len(generated["public_tasks"]),
                       generator=config["models"]["material_generator"]["model"], review_mode="assistant")
        write_json(out / "summary.json", summary)
        if stage != "generate":
            raise DataError("Assistant-review mode stops at generation; import reviewed proposals before solver execution")
        return summary
    task_review_gate(generated["review"], generated["proposal"])
    for task in generated["public_tasks"]:
        leak_scan(task, material)
        write_json(out / "public" / (task["task_id"] + ".json"), task)
    write_json(out / "public/tasks.json", generated["public_tasks"])
    summary.update(status="tasks_ready_pending_solver", tasks_generated=len(generated["public_tasks"]))
    if stage == "generate":
        write_json(out / "summary.json", summary)
        return summary
    validations = []
    private_tasks = {t["task_id"]: t for t in generated["proposal"]["tasks"]}
    for task in generated["public_tasks"]:
        tid = task["task_id"]
        trajectory = checked_stage(out, "solve_" + tid, identity | {"task": task},
            lambda: solve(task, records, model, config, out))
        write_json(out / "private" / ("trajectory_" + tid + ".json"), trajectory)
        reference_task = private_tasks[tid]
        numeric = validate_answer(reference_task, material, records, trajectory)
        judge_payload = {"task": task, "answer": trajectory["answer"], "observations": trajectory["observations"],
            "reference_interpretations": [r for r in material["interpretations"] if r["interpretation_id"] in reference_task["interpretation_ids"]],
            "hard_checks": numeric}
        semantic = None
        if trajectory["answer"] is not None:
            semantic = checked_stage(out, "judge_" + tid, identity | {"payload": judge_payload},
                lambda: model.call("material_judge", judge_payload, "answer_review"))
            validate("answer_review", semantic)
            ids = [c["interpretation_id"] for c in semantic["criteria"]]
            if semantic["task_id"] != tid or len(ids) != len(set(ids)) or set(ids) != set(reference_task["interpretation_ids"]):
                raise DataError("Semantic judge coverage mismatch")
        passed = bool(numeric["hard_pass"] and semantic and semantic["decision"] == "pass"
                      and all(c["pass"] for c in semantic["criteria"]))
        status = "fixture_only" if model.mode == "mock" else ("pilot_pass" if passed else "pilot_fail")
        item = {"task_id": tid, "status": status, "hard_validation": numeric, "semantic_review": semantic,
                "limitations": ["One solver rollout, not a pass-rate estimate.",
                    "Same configured model may perform generator/solver/judge roles; this is not independent expert validation.",
                    "Interpretive reference is an audited evidence-boundary rubric, not an independently verified physical cause."]}
        validations.append(item)
        write_json(out / "private" / ("validation_" + tid + ".json"), item)
    summary.update(status="pilot_complete" if model.mode != "mock" else "fixture_only",
        trajectories=len(validations), pilot_passed=sum(v["status"] == "pilot_pass" for v in validations),
        pilot_failed=sum(v["status"] == "pilot_fail" for v in validations))
    write_json(out / "validation_results.json", {"material_id": material["material_id"], "results": validations})
    write_json(out / "summary.json", summary)
    write_json(out / "bundle.private.json", {"schema_version": "0.2", "summary": summary,
        "material": material, "public_tasks": generated["public_tasks"], "generation": generated,
        "trajectories": [read_json(out / "private" / ("trajectory_" + t["task_id"] + ".json")) for t in generated["public_tasks"]],
        "validations": validations, "warning": "Contains reference answers and original source identities. Never give this bundle to the solver."})
    return summary


def run_batch(manifest_path: Path, config: dict, model, out: Path, project_root: Path, stage: str = "all"):
    validate("material_config", config)
    manifest = read_json(manifest_path)
    validate("material_batch", manifest)
    if len({c["case_id"] for c in manifest["cases"]}) != len(manifest["cases"]):
        raise DataError("Duplicate batch case IDs")
    # Manifest-level lineage check protects future batching and split assignment.
    groups = {}
    sources = {}
    for item in manifest["cases"]:
        recipe = read_json(manifest_path.parent / item["recipe_path"])
        split = recipe["split"]
        for record in recipe["records"]:
            key = record["lineage_group"]
            if key in groups and groups[key] != split:
                raise DataError("A lineage crosses batch splits")
            groups[key] = split
            sha = record["source_hashes"]["telemetry"]
            if sha in sources and sources[sha] != (key, split):
                raise DataError("Identical source has inconsistent lineage/split")
            sources[sha] = (key, split)
    result = {"schema_version": "0.2", "stage": stage, "cases": [], "errors": []}
    for item in manifest["cases"]:
        try:
            case = run_case(manifest_path.parent / item["recipe_path"], config, model,
                            out / item["case_id"], project_root, stage)
            result["cases"].append({"case_id": item["case_id"], **case})
        except (DataError, ValueError, KeyError, OSError) as error:
            # Isolate a case failure, retain diagnostics, continue other cases.
            result["errors"].append({"case_id": item["case_id"], "type": type(error).__name__, "message": str(error)})
            write_json(out / item["case_id"] / "private/failure.json", {"type": type(error).__name__, "message": str(error)})
        write_json(out / "batch_summary.json", result)
    return result


def audit_drafts(manifest_path: Path, draft_index_path: Path, config: dict, out: Path, project_root: Path):
    """API-free draft audit. Reference replay must never be counted as a solver rollout."""
    class NoModel:
        mode = "offline_draft"
        def call(self, *args, **kwargs):
            raise DataError("API-free draft audit cannot call any model")
    index = read_json(draft_index_path)
    validate("draft_index", index)
    entries = {c["case_id"]: c for c in index["cases"]}
    manifest = read_json(manifest_path)
    if len(entries) != len(index["cases"]) or set(entries) != {c["case_id"] for c in manifest["cases"]}:
        raise DataError("Draft index must cover each material case exactly once")
    result = run_batch(manifest_path, config, NoModel(), out, project_root, "materials")
    result["stage"] = "audit_without_api"
    for case in result["cases"]:
        case_dir = out / case["case_id"]
        try:
            material = read_json(case_dir / "private/material.json")
            records = read_json(case_dir / "private/records.json")
            entry = entries[case["case_id"]]
            proposal = read_json(draft_index_path.parent / entry["proposal_path"])
            identity = {"proposal_sha256": digest(proposal), "authorship": entry["authorship"]}
            checked_stage(case_dir, "draft_identity", identity, lambda: identity)
            verify_proposal(proposal, material)
            write_json(case_dir / "private/draft_proposal.json", proposal)
            facts = {f["fact_id"]: f for f in material["facts"]}
            rules = {r["interpretation_id"]: r for r in material["interpretations"]}
            public_tasks, validations, replays = [], [], []
            for task in proposal["tasks"]:
                public = public_task(task, material)
                leak_scan(public, material)
                public_tasks.append(public)
                write_json(case_dir / "public" / (task["task_id"] + ".json"), public)
                tool = MaterialTools(records, task["required_record_ids"])
                observations = {i: tool.call(facts[i]["query"]) for i in task["measurement_ids"]}
                answer = {"measurements": [{"measurement_id": i, "value": observations[i]["result"]["value"],
                    "observation_id": observations[i]["observation_id"]} for i in task["measurement_ids"]],
                    "interpretations": [{"interpretation_id": i, "verdict": rules[i]["expected_verdict"],
                        "explanation": rules[i]["rationale"], "observation_ids": [observations[f]["observation_id"] for f in rules[i]["fact_ids"]]}
                        for i in task["interpretation_ids"]], "limitations": material["limitations"]}
                replay = {"task_id": task["task_id"], "answer": answer, "observations": tool.observations,
                    "provenance": "Deterministic reference replay using private rubric. NOT an independent solver or LLM output."}
                hard = validate_answer(task, material, records, replay)
                if not hard["hard_pass"]:
                    raise DataError("Reference/tool consistency audit failed")
                negatives = []
                for defect in ("wrong_number", "fake_citation", "missing_measurement", "wrong_interpretation"):
                    corrupted = deepcopy(replay)
                    if defect == "wrong_number":
                        item = next(i for i in corrupted["answer"]["measurements"] if i["value"] is not None)
                        item["value"] += 1
                    elif defect == "fake_citation":
                        corrupted["answer"]["measurements"][0]["observation_id"] = "O_fabricated"
                    elif defect == "missing_measurement":
                        corrupted["answer"]["measurements"].pop()
                    else:
                        item = corrupted["answer"]["interpretations"][0]
                        item["verdict"] = "refuted" if item["verdict"] != "refuted" else "supported"
                    detected = not validate_answer(task, material, records, corrupted)["hard_pass"]
                    negatives.append({"defect": defect, "rejected": detected})
                if not all(n["rejected"] for n in negatives):
                    raise DataError("Validator failed a negative control")
                validation = {"task_id": task["task_id"], "status": "draft_checked_pending_solver",
                    "schema_and_evidence_coverage": "pass", "public_private_structural_scan": "pass",
                    "reference_tool_consistency": hard, "validator_negative_controls": negatives,
                    "independent_model_solve": "not_run_user_requested_no_api_test",
                    "model_semantic_review": "not_run_user_requested_no_api_test",
                    "semantic_leakage_review": "requires researcher review; structural scan alone is insufficient",
                    "limitation": "Reference replay checks the measurement/evaluator path. It does not establish that an independent model can solve this task."}
                validations.append(validation); replays.append(replay)
                write_json(case_dir / "private" / ("reference_replay_" + task["task_id"] + ".json"), replay)
                write_json(case_dir / "private" / ("validation_" + task["task_id"] + ".json"), validation)
            write_json(case_dir / "public/tasks.json", public_tasks)
            write_json(case_dir / "validation_results.json", {"material_id": material["material_id"], "results": validations})
            case.update(status="drafts_checked_pending_solver", tasks_generated=0, tasks_authored=len(public_tasks),
                        draft_checks_passed=len(validations), reference_replays=len(replays), trajectories=0, pilot_passed=0,
                        api_calls_in_this_run=0, authorship=entry["authorship"])
            write_json(case_dir / "summary.json", case)
            write_json(case_dir / "bundle.private.json", {"schema_version": "0.2", "summary": case,
                "material": material, "public_tasks": public_tasks, "draft_proposal": proposal,
                "reference_replays": replays, "validations": validations,
                "warning": "Includes private answers and source identities. No independent model rollout or model semantic review was run."})
        except (DataError, ValueError, KeyError, OSError) as error:
            result["errors"].append({"case_id": case["case_id"], "type": type(error).__name__, "message": str(error)})
    write_json(out / "batch_summary.json", result)
    return result
