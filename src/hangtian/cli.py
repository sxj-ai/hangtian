"""Repository-oriented command-line entry point; no implicit cloud calls."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from .contracts import export_schemas, validate
from .data import DataError
from .factory import run
from .models import DeepSeekModel, MockModel


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hangtian")
    commands = parser.add_subparsers(dest="command", required=True)
    schema_cmd = commands.add_parser("schemas", help="Export runtime JSON schemas")
    schema_cmd.add_argument("--out", type=Path, required=True)
    factory = commands.add_parser("run", help="Run the bounded case/task factory")
    factory.add_argument("--manifest", type=Path, required=True)
    factory.add_argument("--config", type=Path, default=Path("configs/pipeline.example.json"))
    factory.add_argument("--project-root", type=Path, default=Path.cwd())
    factory.add_argument("--out", type=Path, required=True)
    factory.add_argument("--backend", choices=("mock", "deepseek"), default="mock")
    factory.add_argument("--allow-remote", action="store_true")
    factory.add_argument("--allow-data-egress", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "schemas":
            export_schemas(args.out)
            return 0
        config = json.loads(args.config.read_text(encoding="utf-8"))
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        validate("manifest", manifest)
        if not 1 <= config["max_cases"] <= 1000 or not 0 <= config["max_revisions"] <= 3:
            raise DataError("Unsafe case/revision budget")
        model = MockModel() if args.backend == "mock" else DeepSeekModel(
            config, args.project_root, args.out, args.allow_remote, args.allow_data_egress)
        result = run(manifest, args.manifest.parent, config, model, args.out, args.project_root)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2 if result["counts"]["failed_packages"] else 0
    except (DataError, OSError, ValueError, KeyError) as error:
        print(f"hangtian: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
