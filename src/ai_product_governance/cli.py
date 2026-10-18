"""`aipg`: command-line interface for the AI Product Governance toolkit."""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
import zipfile
from datetime import date
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


def _iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"'{value}' is not a date in YYYY-MM-DD form") from None


def _never_crash_on_encoding() -> None:
    """Records and policies may contain characters the console cannot encode (e.g. cp1252 on Windows)."""
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        with contextlib.suppress(ValueError, OSError):
            reconfigure(errors="replace")


def _cmd_record_new(args: argparse.Namespace) -> int:
    from ai_product_governance.records import (
        RECORDS_DIR,
        ProhibitedUseCaseError,
        RecordError,
        check_record,
        new_record,
        policy_for_record,
        write_record,
    )

    _never_crash_on_encoding()
    engine = engines.risk_tier()
    out = Path(args.out) if args.out else RECORDS_DIR / f"{args.id}.json"
    if out.name != f"{args.id}.json":
        print(f"error: --out must name the file {args.id}.json so `aipg check` can match it to the id", file=sys.stderr)
        return 2
    if out.exists() and not args.force:
        print(f"error: {out} already exists; pass --force to replace it", file=sys.stderr)
        return 2
    try:
        policy = policy_for_record(out, args.policy)
    except engine.PolicyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3
    try:
        source = sys.stdin.read() if args.answers == "-" else Path(args.answers).read_text(encoding="utf-8")
        record, result = new_record(
            json.loads(source),
            args.id,
            policy,
            on=args.date or date.today(),
            title=args.title or "",
            owner=args.owner,
            answered_by=args.answered_by,
        )
    except ProhibitedUseCaseError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except (OSError, ValueError, RecordError, engine.AnswerError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    write_record(out, record)
    print(f"wrote {out}")
    print(f"{record['title']}: {result['tier']['name']} tier under {policy.label}, from the {policy.source}")
    if result["unanswered_questions"]:
        print("unanswered questions: " + ", ".join(result["unanswered_questions"]))
    outstanding = len(check_record(out, policy, args.date or date.today()).problems)
    print(f"{outstanding} item(s) to resolve before `aipg check` passes; list them with `aipg check {out}`.")
    return 0


def _cmd_check(args: argparse.Namespace) -> int:
    from ai_product_governance.records import (
        RECORDS_DIR,
        RecordError,
        check_records,
        find_records,
        render_json,
        render_markdown,
        render_text,
    )

    _never_crash_on_encoding()
    try:
        paths = find_records([Path(p) for p in args.paths] or ([RECORDS_DIR] if RECORDS_DIR.is_dir() else []))
    except RecordError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if not paths:
        where = ", ".join(args.paths) or RECORDS_DIR.as_posix()
        print(f"error: no use-case records found in {where}; create one with `aipg record new`", file=sys.stderr)
        return 2
    results = check_records(paths, args.policy, args.as_of or date.today())
    render = {"md": render_markdown, "json": render_json}.get(args.format, render_text)
    sys.stdout.write(render(results))
    return 0 if all(result.passed for result in results) else 1


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

    p = sub.add_parser("record", help="create use-case governance records")
    record = p.add_subparsers(dest="record_command", required=True)
    q = record.add_parser("new", help="classify answers and write .ai-governance/use-cases/<id>.json")
    q.add_argument("--answers", metavar="FILE", required=True, help="questionnaire answers as JSON ('-' for stdin)")
    q.add_argument("--id", required=True, help="record ID: lowercase letters, digits and hyphens")
    q.add_argument("--title", metavar="TEXT", help="use-case title (default: derived from the ID)")
    q.add_argument("--owner", metavar="NAME", default="", help="accountable owner of the use case")
    q.add_argument("--answered-by", metavar="NAME", default="", help="who answered the questionnaire")
    q.add_argument("--date", metavar="DATE", type=_iso_date, help="date of the assessment, YYYY-MM-DD (default: today)")
    q.add_argument("--policy", metavar="FILE", help="policy (default: $AIPG_POLICY, the workspace's, bundled)")
    q.add_argument(
        "--out", metavar="FILE", help="where to write the record (default: .ai-governance/use-cases/<id>.json)"
    )
    q.add_argument("--force", action="store_true", help="replace an existing record")
    q.set_defaults(func=_cmd_record_new)

    p = sub.add_parser("check", help="fail unless every use-case record is complete and current under the policy")
    p.add_argument(
        "paths",
        nargs="*",
        metavar="PATH",
        help="record files, use-cases folders or workspaces (default: .ai-governance/use-cases)",
    )
    p.add_argument("--policy", metavar="FILE", help="policy (default: $AIPG_POLICY, each record's workspace, bundled)")
    p.add_argument(
        "--as-of",
        metavar="DATE",
        type=_iso_date,
        help="judge re-certification on this date, YYYY-MM-DD (default: today)",
    )
    p.add_argument("--format", choices=("text", "md", "json"), default="text", help="md suits a pull-request comment")
    p.set_defaults(func=_cmd_check)

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
