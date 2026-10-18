"""A stand-in for the Claude Code CLI used by the tests (never calls a model).

* `auth status` succeeds.
* With `--json-schema` it acts as the judge: every criterion passes if the graded response
  contains "No-go", otherwise every criterion fails.
* Otherwise it acts as a subject: if the skill is installed in the workspace it "activates"
  it, reads the Gate 4 playbook and answers well; without the skill it answers badly.

Every invocation is appended to $FAKE_CLAUDE_LOG as JSON so tests can inspect arguments,
the working directory and the environment the provider passed.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path


def main() -> int:
    args = sys.argv[1:]
    prompt = "" if args[:2] == ["auth", "status"] else sys.stdin.read()
    log = os.environ.get("FAKE_CLAUDE_LOG")
    if log:
        with open(log, "a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "args": args,
                        "cwd": os.getcwd(),
                        "has_claudecode": "CLAUDECODE" in os.environ,
                        "has_host_var": "CLAUDE_CODE_ENTRYPOINT" in os.environ,
                        "has_api_key": "ANTHROPIC_API_KEY" in os.environ,
                        "has_oauth_token": "CLAUDE_CODE_OAUTH_TOKEN" in os.environ,
                    }
                )
                + "\n"
            )
    if args[:2] == ["auth", "status"]:
        print(json.dumps({"loggedIn": True, "authMethod": "claude.ai"}))
        return 0

    if "--json-schema" in args:
        response = prompt.split("<response>", 1)[-1]
        good = "No-go" in response
        ids = sorted(set(re.findall(r"\[(C\d+)\]", prompt)))
        verdicts = [{"id": cid, "verdict": "pass" if good else "fail", "evidence": "", "rationale": ""} for cid in ids]
        print(
            json.dumps(
                {
                    "type": "result",
                    "subtype": "success",
                    "is_error": False,
                    "result": "",
                    "structured_output": {"verdicts": verdicts},
                    "num_turns": 1,
                    "total_cost_usd": 0.01,
                    "usage": {"input_tokens": 900, "output_tokens": 120},
                }
            )
        )
        return 0

    skill = Path.cwd() / ".claude" / "skills" / "ai-product-governance"
    events: list[dict[str, object]] = [{"type": "system", "subtype": "init", "model": "claude-opus-5-5"}]
    if skill.is_dir():
        playbook = skill / "references" / "gate-4-launch-readiness.md"
        events += [
            {
                "type": "assistant",
                "message": {
                    "model": "claude-opus-5-5",
                    "content": [
                        {"type": "tool_use", "id": "t1", "name": "Skill", "input": {"skill": "ai-product-governance"}}
                    ],
                },
            },
            {
                "type": "assistant",
                "message": {
                    "model": "claude-opus-5-5",
                    "content": [
                        {"type": "tool_use", "id": "t2", "name": "Read", "input": {"file_path": str(playbook)}}
                    ],
                },
            },
        ]
        text = "Verdict: No-go. Blocking gaps: kill switch untested, no red team."
    else:
        text = "Sounds fine, go ahead."
    events.append(
        {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "result": text,
            "num_turns": 3,
            "total_cost_usd": 0.05,
            "usage": {"input_tokens": 1000, "output_tokens": 400, "cache_read_input_tokens": 200},
        }
    )
    for event in events:
        print(json.dumps(event))
    return 0


if __name__ == "__main__":
    sys.exit(main())
