"""A stand-in for headless agent CLIs (Codex, Gemini CLI, Copilot CLI, Cursor CLI) used by the tests.

It reads the prompt the way the profile delivers it (stdin, or the value after -p), answers
well only when the skill is installed in the workspace, acts as a judge when asked for JSON,
and writes the answer where the profile expects it (an -o file, a JSON object, or plain text).
Every call is appended to $FAKE_AGENT_LOG.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path


def main() -> int:
    args = sys.argv[1:]
    log = os.environ.get("FAKE_AGENT_LOG")
    if args[:2] == ["login", "status"] or args == ["status"]:
        print("Logged in")
        return 0

    prompt_from_flag = args[args.index("-p") + 1] if "-p" in args else ""
    stdin = "" if sys.stdin is None or sys.stdin.isatty() else sys.stdin.read()
    prompt = (stdin + "\n" + prompt_from_flag).strip()
    if log:
        with open(log, "a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {"args": args, "stdin": stdin, "cwd": os.getcwd(), "has_claudecode": "CLAUDECODE" in os.environ}
                )
                + "\n"
            )

    if "Reply with only a JSON object" in prompt:
        response = prompt.split("<response>", 1)[-1]
        good = "No-go" in response
        ids = sorted(set(re.findall(r"\[(C\d+)\]", prompt)))
        verdicts = [{"id": cid, "verdict": "pass" if good else "fail", "evidence": "", "rationale": ""} for cid in ids]
        answer = "Here is the grading:\n```json\n" + json.dumps({"verdicts": verdicts}) + "\n```"
    elif (Path.cwd() / ".agents" / "skills" / "ai-product-governance" / "SKILL.md").is_file():
        answer = "Verdict: No-go. Blocking gaps: kill switch untested, no red team."
    else:
        answer = "Sounds fine, go ahead."

    if "-o" in args:
        Path(args[args.index("-o") + 1]).write_text(answer, encoding="utf-8")
        print("(progress output the harness should ignore)")
    elif "--output-format" in args and args[args.index("--output-format") + 1] == "json":
        print(json.dumps({"response": answer, "result": answer, "stats": {}}))
    else:
        print(answer)
    return 0


if __name__ == "__main__":
    sys.exit(main())
