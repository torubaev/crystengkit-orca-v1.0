from __future__ import annotations

import argparse
from pathlib import Path

from .config import load_config, write_example_config
from .engine import WorkflowEngine


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Strict ORCA TD-DFT workflow")
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("prepare", "run", "slurm", "submit"):
        item = sub.add_parser(command)
        item.add_argument("config")
        item.add_argument("project")
    validate = sub.add_parser("validate-stage")
    validate.add_argument("project")
    validate.add_argument("stage")
    example = sub.add_parser("example-config")
    example.add_argument("path")
    args = parser.parse_args(argv)
    if args.command == "example-config":
        write_example_config(args.path); return 0
    if args.command == "validate-stage":
        project = Path(args.project).resolve()
        engine = WorkflowEngine(load_config(str(project / "config.yaml")), str(project))
        engine.validate_stage(args.stage); engine.write_reports()
        return 0 if engine.records[args.stage].status.value == "COMPLETED" else 2
    engine = WorkflowEngine(load_config(args.config), args.project)
    destination = Path(args.project).resolve() / "config.yaml"
    destination.parent.mkdir(parents=True, exist_ok=True)
    source = Path(args.config).resolve()
    if source != destination:
        destination.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    if args.command == "prepare": engine.prepare()
    elif args.command == "run": engine.run_local()
    elif args.command == "slurm": engine.generate_slurm()
    elif args.command == "submit": engine.submit_slurm()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
