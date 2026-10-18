"""A minimal, provider-neutral Agent Skills host used by the 'with-skill' arm.

It mirrors how skill-compatible tools work: the activated skill's SKILL.md is placed in
context, and the model loads referenced files and runs bundled scripts on demand
(progressive disclosure). Because the host is the same for every model, differences
between subjects come from the models, not from tool-specific integrations.

Sandboxing: file reads are confined to the skill directory; only the two bundled
scripts can run, with an argument list (no shell), a timeout, and an empty working
directory so no workspace policy leaks in.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from typing import Any

from ai_product_governance.evals.providers import ToolSpec
from ai_product_governance.skill import Skill

ALLOWED_SCRIPTS = ("risk_tier.py", "unit_economics.py")
MAX_FILE_CHARS = 100_000
SCRIPT_TIMEOUT_SECONDS = 30

_HOST_PROMPT = """\
You are an AI assistant. The Agent Skill "{name}" is active for this conversation.

Skill description: {description}

The skill's instructions (its SKILL.md) are below. Files the instructions mention live in the skill \
directory: read them with the read_skill_file tool using paths relative to the skill root (for example \
references/gate-0-intake-and-fit.md). Run the skill's scripts with the run_skill_script tool. There is \
no other workspace, so do not ask the user for files.

<skill_instructions>
{body}
</skill_instructions>
"""

TOOLS = [
    ToolSpec(
        name="read_skill_file",
        description="Read a file from the active skill's directory, e.g. references/<name>.md or assets/templates/<name>.md.",
        parameters={
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Path relative to the skill root"}},
            "required": ["path"],
            "additionalProperties": False,
        },
    ),
    ToolSpec(
        name="run_skill_script",
        description=(
            "Run one of the skill's Python scripts with command-line arguments and return its output. "
            "Scripts: risk_tier.py (e.g. ['--questions'] or ['--answers-json', '{...}', '--format', 'md']) and "
            "unit_economics.py (e.g. ['--input-json', '{...}', '--format', 'md'])."
        ),
        parameters={
            "type": "object",
            "properties": {
                "script": {"type": "string", "enum": list(ALLOWED_SCRIPTS)},
                "args": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["script", "args"],
            "additionalProperties": False,
        },
    ),
]


@dataclass
class SkillRuntime:
    skill: Skill
    files_read: list[str] = field(default_factory=list)
    scripts_run: list[str] = field(default_factory=list)

    def system_prompt(self) -> str:
        return _HOST_PROMPT.format(name=self.skill.name, description=self.skill.description, body=self.skill.clean_body)

    def execute(self, name: str, arguments: dict[str, Any]) -> tuple[str, bool]:
        if name == "read_skill_file":
            return self._read(str(arguments.get("path", "")))
        if name == "run_skill_script":
            return self._run(str(arguments.get("script", "")), arguments.get("args", []))
        return f"Error: unknown tool '{name}'.", True

    def _read(self, relative: str) -> tuple[str, bool]:
        root = self.skill.root.resolve()
        target = (root / relative.lstrip("/\\")).resolve()
        if not target.is_relative_to(root):
            return "Error: path is outside the skill directory.", True
        if not target.is_file():
            return f"Error: '{relative}' does not exist in the skill.", True
        self.files_read.append(target.relative_to(root).as_posix())
        return target.read_text(encoding="utf-8")[:MAX_FILE_CHARS], False

    def _run(self, script: str, args: Any) -> tuple[str, bool]:
        if script not in ALLOWED_SCRIPTS:
            return f"Error: unknown script '{script}'. Available: {', '.join(ALLOWED_SCRIPTS)}.", True
        if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
            return "Error: args must be a list of strings.", True
        self.scripts_run.append(script)
        env = {k: v for k, v in os.environ.items() if k != "AIPG_POLICY"}
        with tempfile.TemporaryDirectory() as empty_dir:
            try:
                completed = subprocess.run(  # noqa: S603 - fixed interpreter and allow-listed script, no shell
                    [sys.executable, str(self.skill.scripts_dir / script), *args],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=SCRIPT_TIMEOUT_SECONDS,
                    cwd=empty_dir,
                    env=env,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                return f"Error: {script} timed out after {SCRIPT_TIMEOUT_SECONDS}s.", True
        output = completed.stdout + (f"\n[stderr]\n{completed.stderr}" if completed.stderr else "")
        return f"[exit code {completed.returncode}]\n{output}", completed.returncode != 0
