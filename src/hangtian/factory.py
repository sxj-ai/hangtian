"""Three-role task factory with bounded revisions and separate public/private output."""
from __future__ import annotations

import json
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from . import __version__
from .contracts import validate, verify_case, verify_tasks, verify_critique, recompute, export_task
from .data import DataError, check_lineage, digest, load_csv, write_json
from .mining import detect, group_candidates, make_package
from .models import RoleModel


def append_jsonl(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, allow_nan=False) + "\n")


def run(manifest: dict, base: Path, config: dict, model: RoleModel, out: Path, project_root: Path) -> dict:
    validate("manifest", manifest)
    validate("config", config)
    check_lineage(manifest["experiments"], base)
    if out.exists() and any(out.iterdir()):
        raise DataError("Output directory must be empty; previous runs are never overwritten")
    out.mkdir(parents=True, exist_ok=True)
    counters = {"experiments": 0, "candidates": 0, "groups": 0, "processed_groups": 0,
                "deferred_or_rejected_cases": 0, "task_proposals": 0, "exported_tasks": 0,
                "failed_packages": 0, "unprocessed_groups": 0}
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=project_root,
                                capture_output=True, text=True, timeout=5).stdout.strip() or None
    except (OSError, subprocess.TimeoutExpired):
        commit = None
    write_json(out / "private" / "run.json", {"version": __version__, "git_commit": commit,
        "python": platform.python_version(), "started_at": datetime.now(timezone.utc).isoformat(),
        "mode": model.mode, "config": config, "manifest_sha256": digest(manifest),
        "prompt_hashes": {p.stem: digest(p.read_text(encoding="utf-8")) for p in (project_root / "prompts").glob("*.md")}})
    # The private manifest maps neutral experiment IDs to local data paths; it never reaches an LLM.
    write_json(out / "private" / "source_manifest.json", manifest)
    for entry in manifest["experiments"]:
        data = load_csv(entry, base, config["max_rows"])
        candidates = detect(data, config["mining"])
        groups = group_candidates(candidates, config["mining"])
        counters["experiments"] += 1
        counters["candidates"] += len(candidates)
        counters["groups"] += len(groups)
        write_json(out / "private" / f"candidates_{entry['experiment_id']}.json", candidates)
        for group in groups:
            if counters["processed_groups"] >= config["max_cases"]:
                counters["unprocessed_groups"] += 1
                continue
            counters["processed_groups"] += 1
            package = make_package(data, group, config["mining"])
            pid = package["package_id"]
            write_json(out / "private" / "packages" / f"{pid}.json", package)
            try:
                # Dataset split and lineage are evaluator metadata, not model instructions.
                visible_package = {k: v for k, v in package.items()
                                   if k not in {"split", "lineage_group", "source_sha256", "source_hashes"}}
                case = model.call("case_curator", {"package": visible_package}, "case")
                write_json(out / "private" / "cases" / f"{pid}.json", case)
                verify_case(case, package)
                if case["decision"] != "accept":
                    counters["deferred_or_rejected_cases"] += 1
                    continue
                expected = recompute(package, load_csv(entry, base, config["max_rows"]))
                feedback: list[str] = []
                for revision in range(config["max_revisions"] + 1):
                    payload = {"package": visible_package, "case": case, "feedback": feedback,
                               "max_tasks": 3, "language": config["task_language"]}
                    tasks = model.call("task_generator", payload, "tasks")
                    write_json(out / "private" / "drafts" / f"{pid}_r{revision}.json", tasks)
                    counters["task_proposals"] += len(tasks.get("tasks", [])) if isinstance(tasks.get("tasks"), list) else 0
                    try:
                        verify_tasks(tasks, package)
                    except DataError as error:
                        feedback = [str(error)]
                        append_jsonl(out / "private" / "decisions.jsonl", {"package_id": pid,
                            "revision": revision, "stage": "code_gate", "decision": "revise", "errors": feedback})
                        if revision == config["max_revisions"]:
                            raise
                        continue
                    critique = model.call("task_critic", {"package": visible_package, "case": case,
                        "tasks": tasks, "code_gate": {"passed": True, "facts_recomputed": True}}, "critique")
                    write_json(out / "private" / "reviews" / f"{pid}_r{revision}.json", critique)
                    verify_critique(critique, tasks, package)
                    feedback = [issue["message"] for review in critique["reviews"]
                                if review["decision"] == "revise" for issue in review["issues"]]
                    if any(r["decision"] == "revise" for r in critique["reviews"]) and revision < config["max_revisions"]:
                        feedback = feedback or ["Revise the task according to the critic's unmet requirements."]
                        continue
                    approved = {r["local_id"]: r for r in critique["reviews"] if r["decision"] in {"accept", "basic_only"}}
                    # Recheck immutable source snapshots after all external calls.
                    expected = recompute(package, load_csv(entry, base, config["max_rows"]))
                    for task in tasks["tasks"]:
                        if task["local_id"] not in approved:
                            continue
                        public, private = export_task(task, package, expected, model.mode)
                        category = "basic_tasks" if approved[task["local_id"]]["decision"] == "basic_only" or task["difficulty"] == "basic" else "public_tasks"
                        append_jsonl(out / f"{category}.jsonl", public)
                        append_jsonl(out / "private" / "evaluators.jsonl", private)
                        counters["exported_tasks"] += 1
                    append_jsonl(out / "private" / "decisions.jsonl", {"package_id": pid,
                        "revision": revision, "stage": "critic", "reviews": critique["reviews"]})
                    break
            except (DataError, OSError, ValueError) as error:
                counters["failed_packages"] += 1
                append_jsonl(out / "private" / "failures.jsonl", {"package_id": pid,
                    "error_type": type(error).__name__, "message": str(error)[:500]})
    summary = {"mode": model.mode, "status": "fixture_only" if model.mode == "mock" else "pending_solver_validation",
               "counts": counters, "limitations": ["No real Agent rollout is executed by this task factory.",
                 "Mock outputs test contracts only; critic approval is not final task correctness.",
                 "Source-level lineage checks cannot discover unregistered cropped or transformed duplicates."]}
    write_json(out / "summary.json", summary)
    return summary
