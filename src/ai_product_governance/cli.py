"""`aipg`: command-line interface for the AI Product Governance toolkit."""

from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

from ai_product_governance import __version__, engines


def _cmd_validate(args: argparse.Namespace) -> int:
    from ai_product_governance.skill import find_repo_root
    from ai_product_governance.validate import validate_repository

    repo = Path(args.repo) if args.repo else find_repo_root()
    findings = validate_repository(repo)
    for finding in findings:
        print(finding)
    errors = sum(1 for f in findings if f.level == "error")
    warnings = len(findings) - errors
    print(f"{errors} error(s), {warnings} warning(s)")
    return 1 if errors or (args.strict and warnings) else 0


def _cmd_build(args: argparse.Namespace) -> int:
    from ai_product_governance.adapters import build_outputs, check_outputs, write_outputs
    from ai_product_governance.skill import find_repo_root

    repo = Path(args.repo) if args.repo else find_repo_root()
    outputs = build_outputs(repo)
    if args.check:
        problems = check_outputs(repo, outputs)
        for problem in problems:
            print(problem)
        if problems:
            print("integrations/ is out of date: run `aipg build` and commit the result.")
            return 1
        print(f"integrations/ is up to date ({len(outputs)} files).")
        return 0
    changed = write_outputs(repo, outputs)
    for path in changed:
        print(f"wrote {path}")
    print(f"{len(changed)} file(s) changed, {len(outputs)} generated.")
    return 0


def _cmd_package(args: argparse.Namespace) -> int:
    """Create a deterministic zip of the skill for upload to Claude, ChatGPT and other skill hosts."""
    from ai_product_governance.skill import find_skill_dir, load_skill

    skill_dir = find_skill_dir()
    skill = load_skill(skill_dir)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{skill.name}-skill-v{skill.version}.zip"
    files = sorted(p for p in skill_dir.rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            arcname = f"{skill.name}/{path.relative_to(skill_dir).as_posix()}"
            info = zipfile.ZipInfo(arcname, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o755 if path.suffix == ".py" else 0o644) << 16
            archive.writestr(info, path.read_bytes())
    print(f"wrote {target} ({len(files)} files)")
    return 0


def _cmd_tier(args: argparse.Namespace) -> int:
    argv = ["--format", args.format]
    if args.policy:
        argv += ["--policy", args.policy]
    if args.questions:
        argv.append("--questions")
    elif args.answers_json is not None:
        argv += ["--answers-json", args.answers_json]
    elif args.answers:
        argv += ["--answers", args.answers]
    else:
        print("error: provide --answers, --answers-json or --questions", file=sys.stderr)
        return 2
    return int(engines.risk_tier().main(argv))


def _cmd_economics(args: argparse.Namespace) -> int:
    argv = ["--format", args.format]
    if args.example:
        argv.append("--example")
    elif args.input_json is not None:
        argv += ["--input-json", args.input_json]
    elif args.input:
        argv += ["--input", args.input]
    else:
        print("error: provide --input, --input-json or --example", file=sys.stderr)
        return 2
    return int(engines.unit_economics().main(argv))


def _cmd_serve(args: argparse.Namespace) -> int:
    from ai_product_governance.mcp_server import ServerConfigError, serve

    try:
        serve(
            transport=args.transport,
            host=args.host,
            port=args.port,
            policy_path=args.policy,
            token_file=args.token_file,
            audit_log=args.audit_log,
        )
    except ServerConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


def _cmd_eval(args: argparse.Namespace) -> int:
    from ai_product_governance.evals.cli import run_from_args

    return run_from_args(args)


def _cmd_eval_kit(args: argparse.Namespace) -> int:
    from ai_product_governance.evals.cli import run_kit_from_args

    return run_kit_from_args(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aipg", description="AI Product Governance toolkit")
    parser.add_argument("--version", action="version", version=f"aipg {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("validate", help="validate the skill, policy, links and versions")
    p.add_argument("--repo", help="repository root (default: auto-detect)")
    p.add_argument("--strict", action="store_true", help="treat warnings as errors")
    p.set_defaults(func=_cmd_validate)

    p = sub.add_parser("build", help="generate integrations/ from the skill")
    p.add_argument("--repo", help="repository root (default: auto-detect)")
    p.add_argument("--check", action="store_true", help="fail if integrations/ is out of date instead of writing")
    p.set_defaults(func=_cmd_build)

    p = sub.add_parser("package", help="zip the skill for upload to skill hosts")
    p.add_argument("--out", default="dist", help="output directory (default: dist)")
    p.set_defaults(func=_cmd_package)

    p = sub.add_parser("tier", help="classify a use case into a risk tier")
    p.add_argument("--answers", metavar="FILE")
    p.add_argument("--answers-json", metavar="JSON")
    p.add_argument("--questions", action="store_true")
    p.add_argument("--policy", metavar="FILE")
    p.add_argument("--format", choices=("json", "md"), default="md")
    p.set_defaults(func=_cmd_tier)

    p = sub.add_parser("economics", help="price an AI feature per completed task")
    p.add_argument("--input", metavar="FILE")
    p.add_argument("--input-json", metavar="JSON")
    p.add_argument("--example", action="store_true")
    p.add_argument("--format", choices=("json", "md"), default="md")
    p.set_defaults(func=_cmd_economics)

    p = sub.add_parser("serve", help="run the MCP server")
    p.add_argument("--transport", choices=("stdio", "streamable-http"), default="stdio")
    p.add_argument("--host", default="127.0.0.1", help="interface to listen on; beyond loopback a token is required")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--policy", metavar="FILE", help="policy to enforce (default: $AIPG_POLICY, workspace, bundled)")
    p.add_argument(
        "--token-file",
        metavar="FILE",
        help="file holding the bearer token HTTP clients must send (default: $AIPG_SERVER_TOKEN)",
    )
    p.add_argument("--audit-log", metavar="PATH", help="append one JSON line per tool call to this file")
    p.set_defaults(func=_cmd_serve)

    from ai_product_governance.evals.cli import add_arguments, add_kit_arguments

    p = sub.add_parser("eval", help="run the evals with whichever AI tool you have (auto-detected)")
    add_arguments(p)
    p.set_defaults(func=_cmd_eval)

    p = sub.add_parser("eval-kit", help="run the evals by copy and paste with any chat tool")
    add_kit_arguments(p)
    p.set_defaults(func=_cmd_eval_kit)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
