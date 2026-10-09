"""Validate the NEW private sidecar only; never infer semantic acceptance.

Not an adapter to contracts.CASE, material recipes, or autonomous tasks. Validation
checks integrity of supplied records; it does not recompute data or certify review.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import jsonschema

SCHEMA = Path(__file__).resolve().parents[1]/"docs/case_curation/case_record.schema.json"


def content_digest(record):
    # Status and review are decisions about immutable substantive content.
    payload = {k:v for k,v in record.items() if k not in {"status", "review"}}
    return hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False,allow_nan=False).encode("utf-8")).hexdigest()


def facts_digest(record):
    """Bind raw verification to exact source/query/result facts, excluding verdicts."""
    facts = sorted(({k:v for k,v in item.items() if k != "verification_status"}
                    for item in record["facts"]), key=lambda x:x["fact_id"])
    payload={"facts":facts,"source_artifacts":sorted(record["source_artifacts"],key=lambda x:x["telemetry_sha256"])}
    return hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False,allow_nan=False).encode("utf-8")).hexdigest()


def validate_record(record, artifact_root, source_rows, schema_path=SCHEMA):
    jsonschema.Draft202012Validator(json.loads(schema_path.read_text(encoding="utf-8"))).validate(record)
    hashes = set(record["source_hashes"])
    if not hashes.issubset(source_rows):
        raise ValueError("Unknown source hash")
    artifacts=[x["telemetry_sha256"] for x in record["source_artifacts"]]
    if set(artifacts) != hashes or len(artifacts) != len(hashes):
        raise ValueError("Source artifact coverage mismatch")
    for item in record["windows"] + record["facts"]:
        sha = item["source_sha256"]
        a,b = item["rows"]
        if sha not in hashes or not 0 <= a < b <= source_rows[sha]:
            raise ValueError("Invalid or out-of-scope source rows")
    fact_ids = [x["fact_id"] for x in record["facts"]]
    if len(set(fact_ids)) != len(fact_ids):
        raise ValueError("Duplicate fact ID")
    for claim in record["claims"]:
        if not set(claim["fact_ids"]).issubset(fact_ids):
            raise ValueError("Unknown claim evidence")
        if claim["verdict"] != "untested" and not claim["fact_ids"]:
            raise ValueError("Assessed claims need evidence")
    decision_map = {"accepted":"accept", "merged":"merge", "rejected":"reject"}
    review = record["review"]
    if record["status"] in decision_map:
        if review["decision"] != decision_map[record["status"]] or review["reviewed_content_sha256"] != content_digest(record):
            raise ValueError("Missing or stale review binding")
        if not review["reviewer"] or not review["rationale"] or not review["independence"]:
            raise ValueError("Review provenance missing")
    if record["status"] == "merged":
        if not record["distinction"]["merge_into"] or record["distinction"]["merge_into"] == record["case_id"]:
            raise ValueError("Merge requires another case target")
    if record["status"] == "accepted":
        if (not record["facts"] or not record["windows"] or not record["claims"] or review["blocking_issues"]
            or not any(c["verdict"] != "untested" for c in record["claims"])
            or any(s["alignment"] == "unverified" for s in record["source_artifacts"])
            or record["distinction"]["disposition"] not in {"core","variant"}
            or record["public_scope"]["leakage_review"] != "passed"
            or not record["public_scope"]["record_selection"]
            or any(f["verification_status"] != "passed" for f in record["facts"])):
            raise ValueError("Accepted status lacks evidence, review, or public scope")
        check = record["verification"]
        if check["status"] != "passed" or not check["report_file"] or not check["report_sha256"]:
            raise ValueError("Accepted status requires bound raw verification")
        root = Path(artifact_root).resolve()
        report = (root/check["report_file"]).resolve()
        if root not in report.parents:
            raise ValueError("Verification report outside artifact root")
        payload = report.read_bytes()
        if hashlib.sha256(payload).hexdigest() != check["report_sha256"]:
            raise ValueError("Verification report hash mismatch")
        result = json.loads(payload)
        if (result.get("status") != "passed" or not set(fact_ids).issubset(result.get("checked_fact_ids", []))
            or result.get("checked_facts_sha256") != facts_digest(record)):
            raise ValueError("Verification report lacks checked facts")
    return {"case_id":record["case_id"], "status":record["status"],
            "content_sha256":content_digest(record), "validation":"structural_and_binding_only"}


if __name__ == "__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--record",type=Path,required=True)
    p.add_argument("--inventory",type=Path,required=True,help="capacity_inventory.private.json")
    p.add_argument("--artifact-root",type=Path,required=True)
    args=p.parse_args()
    inventory=json.loads(args.inventory.read_text(encoding="utf-8"))
    rows={x["telemetry_sha256"]:x["rows"] for x in inventory["sources"]}
    print(json.dumps(validate_record(json.loads(args.record.read_text(encoding="utf-8")),args.artifact_root,rows),ensure_ascii=False))
