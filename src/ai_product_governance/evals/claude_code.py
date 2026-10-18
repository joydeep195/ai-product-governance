"""Claude Code as an eval subject and judge: your Claude login, no API key.

Runs `claude -p` (headless mode), which authenticates with the Claude subscription you
signed in with (`claude auth login`) or a `CLAUDE_CODE_OAUTH_TOKEN` from
`claude setup-token` in CI. Usage counts against your plan's limits instead of being
billed per token.

Unlike the API providers, this is a *native* skill host: in the with-skill arm the skill
is installed into a throwaway workspace at `.claude/skills/`, and Claude Code discovers,
activates and follows it exactly as it would for a user. The stream of tool calls tells
us whether the skill was activated, which playbooks were read and which scripts ran.

Isolation without bare mode (bare mode cannot use a subscription login):
  * each run happens in a fresh, empty temporary workspace;
  * `--setting-sources project` keeps your personal settings, skills, plugins, hooks and
    CLAUDE.md out of the run;
  * `--no-session-persistence` keeps eval runs out of your session history;
  * `--permission-mode dontAsk --permission-prompts none` denies anything not allowed:
    the with-skill arm may only run Python (the skill's calculators); the baseline arm and
    the judge get no tools at all;
  * variables from a surrounding Claude Code session (for example CLAUDECODE) and any API
    keys are removed from the child environment, so the run really uses your login.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Any

from ai_product_governance.evals.config import ModelSpec
from ai_product_governance.evals.providers import AgentResult, ProviderError, ToolCall, Usage

CLAUDE_BIN_ENV = "AIPG_CLAUDE_BIN"
SKILL_TOOLS = "Skill,Read,Glob,Grep,Bash"
SCRIPT_RULES = ("Bash(python *)", "Bash(python3 *)", "Bash(py *)")
# CLAUDE_CODE_* variables a user sets on purpose; every other one belongs to a host session.
_USER_CLAUDE_VARS = frozenset(
    {"CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY"}
)


def find_claude_cli() -> list[str] | None:
    """Locate the Claude Code CLI: $AIPG_CLAUDE_BIN, `claude` on PATH, or the copy bundled with Claude Desktop."""
    explicit = os.environ.get(CLAUDE_BIN_ENV)
    if explicit:
        return [explicit]
    on_path = shutil.which("claude")
    if on_path:
        return [on_path]
    roots = []
    if os.environ.get("APPDATA"):
        roots.append(Path(os.environ["APPDATA"]) / "Claude" / "claude-code")
    roots.append(Path.home() / "Library" / "Application Support" / "Claude" / "claude-code")
    candidates = [
        exe
        for root in roots
        if root.is_dir()
        for pattern in ("*/*/claude.exe", "*/*/claude")
        for exe in root.glob(pattern)
        if exe.is_file()
    ]
    if not candidates:
        return None
    return [str(max(candidates, key=lambda exe: _version_key(exe.parent.parent.name)))]


def _version_key(name: str) -> tuple[int, ...]:
    parts = []
    for piece in name.split("."):
        parts.append(int(piece) if piece.isdigit() else -1)
    return tuple(parts)


class ClaudeCodeProvider:
    reports_tool_calls = True  # stream-json exposes every tool call, so skill adherence can be measured

    def __init__(self, spec: ModelSpec) -> None:
        params = spec.params
        command = params.get("command")
        if isinstance(command, str):
            self.command = [command]
        elif isinstance(command, list) and command:
            self.command = [str(part) for part in command]
        else:
            self.command = find_claude_cli() or ["claude"]
        self.spec = spec
        self.model = None if spec.model in ("", "inherit") else spec.model
        effort = params.get("effort")
        self.effort = None if effort in (None, "", "inherit") else str(effort)
        self.timeout = float(params.get("timeout_seconds", 1200))
        self.use_subscription = bool(params.get("use_subscription", True))
        self._slots = threading.BoundedSemaphore(int(params.get("max_parallel", 2)))

    # ------------------------------------------------------------------ environment

    def environment(self) -> dict[str, str]:
        env = {}
        for key, value in os.environ.items():
            if key == "CLAUDECODE" or (key.startswith("CLAUDE_CODE_") and key not in _USER_CLAUDE_VARS):
                continue
            if self.use_subscription and key in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
                continue
            env[key] = value
        return env

    def check_ready(self) -> tuple[bool, str]:
        try:
            completed = subprocess.run(  # noqa: S603 - fixed argument list, no shell
                [*self.command, "auth", "status"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
                env=self.environment(),
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return False, f"cannot start the Claude Code CLI ({exc}); install it or set {CLAUDE_BIN_ENV}"
        if completed.returncode == 0:
            return True, "signed in to Claude Code"
        if self.environment().get("CLAUDE_CODE_OAUTH_TOKEN"):
            return True, "CLAUDE_CODE_OAUTH_TOKEN is set"
        return False, f"Claude Code is not signed in: run `{' '.join(self.command)} auth login` once"

    # ------------------------------------------------------------------ runs

    def _base_args(self, max_turns: int) -> list[str]:
        args = [
            *self.command,
            "-p",
            "--no-session-persistence",
            "--setting-sources",
            "project",
            "--permission-mode",
            "dontAsk",
            "--permission-prompts",
            "none",
            "--max-turns",
            str(max_turns),
        ]
        if self.model:
            args += ["--model", self.model]
        if self.effort:
            args += ["--effort", self.effort]
        return args

    def _invoke(self, args: list[str], prompt: str, cwd: Path) -> subprocess.CompletedProcess[str]:
        with self._slots:
            try:
                return subprocess.run(  # noqa: S603 - fixed argument list, prompt passed on stdin
                    args,
                    input=prompt,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=self.timeout,
                    cwd=cwd,
                    env=self.environment(),
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise ProviderError(f"Claude Code timed out after {self.timeout:.0f}s") from exc

    def run_native(
        self, prompt: str, skill_root: Path | None, append_system_prompt: str, max_turns: int
    ) -> AgentResult:
        """Run one prompt; with `skill_root`, the skill is installed where Claude Code discovers project skills."""
        with (
            tempfile.TemporaryDirectory(prefix="aipg-run-") as run_dir,
            tempfile.TemporaryDirectory(prefix="aipg-ctx-") as context_dir,
        ):
            workspace = Path(run_dir)
            system_file = Path(context_dir) / "append-system-prompt.md"
            system_file.write_text(append_system_prompt, encoding="utf-8")
            args = [
                *self._base_args(max_turns),
                "--output-format",
                "stream-json",
                "--verbose",
                "--append-system-prompt-file",
                str(system_file),
            ]
            if skill_root is not None:
                target = workspace / ".claude" / "skills" / skill_root.name
                shutil.copytree(skill_root, target, ignore=shutil.ignore_patterns("__pycache__"))
                args += ["--tools", SKILL_TOOLS, "--allowedTools", *SCRIPT_RULES]
            else:
                args += ["--tools", ""]
            completed = self._invoke(args, prompt, workspace)
        return parse_stream(completed.stdout, completed.stderr)

    def complete_json(self, system: str, user: str, schema: dict[str, Any], schema_name: str) -> tuple[Any, Usage]:
        with tempfile.TemporaryDirectory(prefix="aipg-judge-") as run_dir:
            workspace = Path(run_dir)
            system_file = workspace / "system-prompt.md"
            system_file.write_text(system, encoding="utf-8")
            args = [
                *self._base_args(max_turns=4),
                "--output-format",
                "json",
                "--json-schema",
                json.dumps(schema),
                "--system-prompt-file",
                str(system_file),
                "--tools",
                "",
            ]
            completed = self._invoke(args, user, workspace)
        payload = _last_json_object(completed.stdout)
        if payload is None or payload.get("is_error"):
            detail = (payload or {}).get("result") or completed.stderr.strip()[-300:] or "no output"
            raise ProviderError(f"Claude Code judge failed: {detail}")
        structured = payload.get("structured_output")
        if structured is None:
            try:
                structured = json.loads(payload.get("result") or "")
            except json.JSONDecodeError as exc:
                raise ProviderError("Claude Code judge returned no structured output") from exc
        return structured, _usage(payload)

    def run_agent(self, *args: Any, **kwargs: Any) -> AgentResult:
        raise ProviderError("Claude Code loads skills natively; the runner uses run_native for this provider")


# ---------------------------------------------------------------------- parsing


def parse_stream(stdout: str, stderr: str = "") -> AgentResult:
    """Turn `--output-format stream-json` output into an AgentResult with the tool calls Claude made."""
    result = AgentResult(text="")
    final: dict[str, Any] | None = None
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = event.get("type")
        if kind == "system" and event.get("subtype") == "init":
            result.served_model = str(event.get("model") or result.served_model)
        elif kind == "assistant":
            message = event.get("message") or {}
            result.served_model = str(message.get("model") or result.served_model)
            for block in message.get("content") or []:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    raw_input = block.get("input")
                    arguments: dict[str, Any] = raw_input if isinstance(raw_input, dict) else {}
                    result.tool_calls.append(ToolCall(str(block.get("name", "")), arguments, "", False))
        elif kind == "result":
            final = event
    if final is None:
        result.error = "Claude Code produced no result: " + (stderr.strip()[-300:] or "empty output")
        return result
    result.text = str(final.get("result") or "")
    result.turns = int(final.get("num_turns") or 0)
    result.stop_reason = str(final.get("subtype") or "")
    result.usage = _usage(final)
    if final.get("is_error") or final.get("subtype") != "success":
        result.error = f"{final.get('subtype') or 'error'}: {result.text[:300]}"
    return result


def _usage(payload: dict[str, Any]) -> Usage:
    usage = payload.get("usage") or {}
    cache_read = int(usage.get("cache_read_input_tokens") or 0)
    cache_write = int(usage.get("cache_creation_input_tokens") or 0)
    cost = payload.get("total_cost_usd")
    return Usage(
        input_tokens=int(usage.get("input_tokens") or 0) + cache_read + cache_write,
        output_tokens=int(usage.get("output_tokens") or 0),
        cache_read_tokens=cache_read,
        reported_cost_usd=float(cost) if isinstance(cost, (int, float)) else None,
    )


def _last_json_object(stdout: str) -> dict[str, Any] | None:
    for line in reversed(stdout.strip().splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                return value
    try:
        value = json.loads(stdout)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def native_adherence(tool_calls: list[ToolCall], skill_name: str) -> tuple[bool, list[str], list[str]]:
    """From native tool calls: was the skill activated, which skill files were read, which scripts ran."""
    activated = any(call.name == "Skill" and skill_name in json.dumps(call.arguments) for call in tool_calls)
    marker = f"/.claude/skills/{skill_name}/"
    files_read = []
    for call in tool_calls:
        if call.name == "Read":
            path = str(call.arguments.get("file_path", "")).replace("\\", "/")
            if marker in path:
                files_read.append(path.split(marker, 1)[1])
    commands = " ".join(str(call.arguments.get("command", "")) for call in tool_calls if call.name == "Bash")
    scripts_run = [script for script in ("risk_tier.py", "unit_economics.py") if script in commands]
    return activated, files_read, scripts_run
