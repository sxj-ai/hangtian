"""Interchangeable role models; remote calls are opt-in and never executed in tests."""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol
from .contracts import schema
from .data import DataError, digest, write_json


class RoleModel(Protocol):
    mode: str
    def call(self, role: str, payload: dict, kind: str) -> dict: ...


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward authorization to an unexpected host.


class DeepSeekModel:
    mode = "remote"

    def __init__(self, config: dict, project_root: Path, out: Path,
                 allow_remote: bool = False, allow_data_egress: bool = False):
        if not (allow_remote and allow_data_egress):
            raise DataError("Remote calls require both --allow-remote and --allow-data-egress")
        self.config, self.root, self.out = config, project_root, out
        self.calls = 0
        self.metadata: list[dict] = []

    def call(self, role: str, payload: dict, kind: str) -> dict:
        settings = self.config["models"][role]
        url = urllib.parse.urlsplit(settings["base_url"])
        if url.scheme != "https" or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise DataError("Model base_url must be an explicit HTTPS endpoint without URL credentials")
        key = os.environ.get(settings["api_key_env"])
        if not key or key == "replace_locally_never_commit":
            raise DataError("API key environment variable is missing")
        prompt = (self.root / "prompts" / f"{role}.md").read_text(encoding="utf-8")
        system = prompt + "\n\nJSON_OUTPUT_SCHEMA:\n" + json.dumps(schema(kind), ensure_ascii=False)
        user = "UNTRUSTED_INPUT_JSON\n" + json.dumps(payload, ensure_ascii=False, allow_nan=False)
        if len(user.encode()) > self.config["max_input_bytes"]:
            raise DataError("Model input budget exceeded; do not truncate evidence silently")
        body = {"model": settings["model"], "messages": [{"role": "system", "content": system},
                {"role": "user", "content": user}], "response_format": {"type": "json_object"},
                "max_tokens": settings["max_tokens"], "temperature": settings["temperature"],
                "thinking": {"type": "disabled"}, "stream": False}
        opener = urllib.request.build_opener(NoRedirect())
        for attempt in range(self.config["transport_retries"] + 1):
            if self.calls >= self.config["max_api_calls"]:
                raise DataError("API call budget exhausted (including transport retries)")
            self.calls += 1
            record = {"call_index": self.calls, "role": role, "timestamp": datetime.now(timezone.utc).isoformat(),
                      "requested_model": settings["model"], "endpoint": settings["base_url"],
                      "prompt_sha256": digest(system), "input_sha256": digest(payload),
                      "parameters": {"temperature": settings["temperature"], "max_tokens": settings["max_tokens"]},
                      "attempt": attempt, "status": "started"}
            call_path = self.out / "private" / "calls" / f"{self.calls:05d}.json"
            write_json(call_path, {"metadata": record, "input": payload})
            start = time.monotonic()
            try:
                req = urllib.request.Request(settings["base_url"].rstrip("/") + "/chat/completions",
                    data=json.dumps(body, allow_nan=False).encode(), method="POST",
                    headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
                with opener.open(req, timeout=self.config["timeout_seconds"]) as response:
                    raw = response.read(self.config["max_response_bytes"] + 1)
                if len(raw) > self.config["max_response_bytes"]:
                    raise DataError("Response budget exceeded")
                envelope = json.loads(raw)
                choice = envelope["choices"][0]
                content = choice["message"].get("content")
                record.update({"response_model": envelope.get("model"), "request_id": envelope.get("id"),
                    "system_fingerprint": envelope.get("system_fingerprint"), "usage": envelope.get("usage", {}),
                    "finish_reason": choice.get("finish_reason"), "latency_seconds": time.monotonic() - start})
                # Do not retain provider reasoning_content; only contract output is required.
                write_json(call_path, {"metadata": record, "input": payload, "output_text": content})
                if choice.get("finish_reason") != "stop" or not content:
                    raise DataError("Incomplete or empty model output")
                result = json.loads(content, parse_constant=lambda _: (_ for _ in ()).throw(DataError("Non-finite JSON")))
                if not isinstance(result, dict):
                    raise DataError("Expected one JSON object")
                record["status"] = "completed"
                self.metadata.append(record)
                write_json(call_path, {"metadata": record, "input": payload, "output": result})
                return result
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as error:
                code = getattr(error, "code", None)
                record.update({"status": "transport_error", "http_status": code,
                               "latency_seconds": time.monotonic() - start})
                self.metadata.append(record)
                write_json(call_path, {"metadata": record})
                retryable = code is None or code in {408, 429, 500, 502, 503, 504}
                if not retryable or attempt >= self.config["transport_retries"]:
                    raise DataError(f"Model transport failed; HTTP status={code}; see private metadata") from None
                time.sleep(min(2 ** attempt, 8))
            except (KeyError, IndexError, json.JSONDecodeError) as error:
                raise DataError(f"Malformed model response ({type(error).__name__})") from None
        raise DataError("No model response")


class MockModel:
    """Deterministic contract fixture, not a language model and not a quality judge."""
    mode = "mock"

    def call(self, role: str, payload: dict, kind: str) -> dict:
        package = payload["package"]
        fid = [f["fact_id"] for f in package["facts"]]
        if role == "case_curator":
            return {"package_id": package["package_id"], "decision": "accept" if fid else "reject",
                    "summary": "OFFLINE FIXTURE: a bounded telemetry comparison scene.", "fact_ids": fid,
                    "hypotheses": [], "limitations": package["limitations"], "requested_context": []}
        if role == "task_generator":
            if not fid:
                return {"package_id": package["package_id"], "tasks": []}
            tasks = []
            for i, kind_name in enumerate(("integrated_investigation", "evidence_sufficiency"), 1):
                tasks.append({"local_id": f"T{i}", "task_type": kind_name,
                    "title": f"OFFLINE FIXTURE {i}: {kind_name}",
                    "prompt": ("Inspect the permitted telemetry records. Compute the explicitly defined measurements, "
                        "compare plausible operational and recording explanations, and state what remains unresolved. "
                        if i == 1 else "Assess whether these observations establish a unique component fault or a command "
                        "execution delay. Cite the supplied record evidence and identify unavailable information."),
                    "observable_goal": "A record-grounded report with measurements, alternatives and limitations.",
                    "fact_ids": fid[:4], "numeric_checks": [{"answer_key": f"m{j}", "fact_id": f}
                        for j, f in enumerate(fid[:2], 1)],
                    "evidence_requirements": ["Cite records supporting each claim; a detector label is not ground truth."],
                    "hypotheses_to_compare": ["Operational change", "Measurement or recording issue"],
                    "limitations_to_address": package["limitations"],
                    "semantic_rubric": [{"criterion": "Separate observations from causal explanations.", "supporting_fact_ids": fid[:2]}],
                    "investigation_decisions": ["Choose additional evidence that could distinguish the alternatives."],
                    "distinctness_rationale": "Fixture-only variation, not independently established semantic novelty.",
                    "difficulty": "guided_investigation"})
            return {"package_id": package["package_id"], "tasks": tasks}
        if role == "task_critic":
            return {"package_id": package["package_id"], "reviews": [
                {"local_id": t["local_id"], "decision": "accept",
                 "scores": {"grounding": 0, "data_dependence": 0, "distinctness": 0, "investigation_value": 0},
                 "issues": [{"severity": "warning", "code": "OTHER", "message": "Mock review does not assess quality.", "fact_ids": []}],
                 "rationale": "OFFLINE FIXTURE: contract path only, never research acceptance."}
                for t in payload["tasks"]["tasks"]]}
        raise DataError("Unknown model role")
