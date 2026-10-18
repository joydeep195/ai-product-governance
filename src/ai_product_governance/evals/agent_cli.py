"""Any agentic AI tool with a headless mode, driven through a declarative profile.

Many AI tools can run a single prompt from the command line using the account you are
already signed in to: OpenAI Codex (ChatGPT login), Gemini CLI (Google login), GitHub
Copilot CLI (Copilot subscription), Cursor CLI (Cursor subscription). Each profile below
describes, as data, how to pass a prompt, where the tool discovers project skills, how to
read the final answer and how to tell whether the user is signed in. Adding a tool means
adding a profile, not writing a provider.

Like Claude Code, these are native skill hosts: in the with-skill arm the skill is copied
into the tool's skills folder inside a throwaway workspace, and the tool decides for itself
whether to use it.

Profiles marked `verified=False` were built from each tool's documentation and are covered
by tests against a fake CLI, but have not yet been run against the real tool. Run
`aipg eval --dry-run` to see what is detected on your machine.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai_product_governance.evals.config import ModelSpec
from ai_product_governance.evals.providers import AgentResult, ProviderError, Usage


@dataclass(frozen=True)
class CliProfile:
    name: str
    title: str
    executables: tuple[str, ...]
    skills_dir: str
    prompt_args: tuple[str, ...]  # "{prompt}" is replaced by the prompt; without it the prompt goes to stdin
    base_args: tuple[str, ...] = ()
    output: str = "text"  # "text" | "file" | "json:<field>"
    output_file_args: tuple[str, ...] = ()  # used with output="file"; "{output_file}" placeholder
    model_args: tuple[str, ...] = ()  # "{model}" placeholder
    effort_args: tuple[str, ...] = ()  # "{effort}" placeholder
    schema_args: tuple[str, ...] = ()  # "{schema_file}" placeholder, for structured judge output
    ready_args: tuple[str, ...] = ()  # a command that exits 0 when signed in
    ready_env: tuple[str, ...] = ()  # any of these environment variables means signed in
    ready_files: tuple[str, ...] = ()  # any of these files (under the home directory) means signed in
    login_hint: str = ""
    verified: bool = False


PROFILES: dict[str, CliProfile] = {
    "codex": CliProfile(
        name="codex",
        title="OpenAI Codex CLI (ChatGPT sign-in)",
        executables=("codex",),
        skills_dir=".agents/skills",
        base_args=(
            "exec",
            "--ephemeral",
            "--skip-git-repo-check",
            "--ignore-user-config",
            "--ignore-rules",
            "--sandbox",
            "read-only",
        ),
        prompt_args=("-",),  # `-` reads the prompt from stdin
        output="file",
        output_file_args=("-o", "{output_file}"),
        model_args=("-m", "{model}"),
        effort_args=("-c", "model_reasoning_effort={effort}"),
        schema_args=("--output-schema", "{schema_file}"),
        ready_args=("login", "status"),
        ready_env=("CODEX_API_KEY",),
        login_hint="codex login",
    ),
    "gemini": CliProfile(
        name="gemini",
        title="Gemini CLI (Google sign-in)",
        executables=("gemini",),
        skills_dir=".agents/skills",
        base_args=("--output-format", "json", "--approval-mode", "default"),
        prompt_args=("-p", "Respond to the request above."),  # the prompt itself arrives on stdin
        output="json:response",
        model_args=("-m", "{model}"),
        ready_env=("GEMINI_API_KEY", "GOOGLE_API_KEY"),
        ready_files=(".gemini/oauth_creds.json",),
        login_hint="run `gemini` once and choose Login with Google",
    ),
    "copilot": CliProfile(
        name="copilot",
        title="GitHub Copilot CLI (Copilot subscription)",
        executables=("copilot",),
        skills_dir=".agents/skills",
        base_args=("-s", "--no-custom-instructions"),
        prompt_args=("-p", "{prompt}"),
        output="text",
        model_args=("--model", "{model}"),
        ready_env=("COPILOT_GITHUB_TOKEN", "GH_TOKEN", "GITHUB_TOKEN"),
        ready_files=(".copilot/config.json",),
        login_hint="run `copilot` once and use /login",
    ),
    "cursor": CliProfile(
        name="cursor",
        title="Cursor CLI (Cursor subscription)",
        executables=("cursor-agent",),
        skills_dir=".agents/skills",
        base_args=("--output-format", "json"),
        prompt_args=("-p", "{prompt}"),
        output="json:result",
        model_args=("--model", "{model}"),
        ready_args=("status",),
        ready_env=("CURSOR_API_KEY",),
        login_hint="cursor-agent login",
    ),
}


_WINDOWS = os.name == "nt"


def _is_batch_file(executable: str) -> bool:
    return _WINDOWS and Path(executable).suffix.lower() in (".bat", ".cmd")


def _scrubbed_environment() -> dict[str, str]:
    """Drop variables that belong to a surrounding Claude Code session; keep everything else."""
    return {
        key: value
        for key, value in os.environ.items()
        if key != "CLAUDECODE" and not (key.startswith("CLAUDE_CODE_") and key != "CLAUDE_CODE_OAUTH_TOKEN")
    }


class AgentCliProvider:
    reports_tool_calls = False  # only the final answer is read, so adherence is not reported

    def __init__(self, spec: ModelSpec) -> None:
        params = spec.params
        profile_name = str(params.get("profile", ""))
        if profile_name not in PROFILES:
            raise ValueError(f"Unknown agent CLI profile '{profile_name}'. Available: {', '.join(PROFILES)}")
        self.spec = spec
        self.profile = PROFILES[profile_name]
        command = params.get("command")
        if isinstance(command, str):
            self.command: list[str] | None = [command]
        elif isinstance(command, list) and command:
            self.command = [str(part) for part in command]
        else:
            found = next((shutil.which(name) for name in self.profile.executables if shutil.which(name)), None)
            self.command = [found] if found else None
        self.model = None if spec.model in ("", "inherit") else spec.model
        effort = params.get("effort")
        self.effort = None if effort in (None, "", "inherit") else str(effort)
        self.timeout = float(params.get("timeout_seconds", 1200))
        self._slots = threading.BoundedSemaphore(int(params.get("max_parallel", 2)))

    # ------------------------------------------------------------------ readiness

    def check_ready(self) -> tuple[bool, str]:
        profile = self.profile
        if self.command is None:
            return False, f"{profile.title} is not installed (looked for {', '.join(profile.executables)} on PATH)"
        if any(os.environ.get(var) for var in profile.ready_env):
            return True, "credentials found in the environment"
        if any((Path.home() / relative).is_file() for relative in profile.ready_files):
            return True, "signed in (saved login found)"
        if profile.ready_args:
            try:
                completed = subprocess.run(  # noqa: S603 - fixed argument list, no shell
                    [*self.command, *profile.ready_args],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=60,
                    env=_scrubbed_environment(),
                    check=False,
                )
            except (OSError, subprocess.SubprocessError) as exc:
                return False, f"cannot start {profile.title} ({exc})"
            if completed.returncode == 0:
                return True, "signed in"
        return False, f"not signed in: {profile.login_hint}"

    # ------------------------------------------------------------------ runs

    def _args(self, prompt: str, output_file: Path, schema_file: Path | None) -> tuple[list[str], str | None]:
        if self.command is None:
            raise ProviderError(f"{self.profile.title} is not installed")
        profile = self.profile
        values = {
            "prompt": prompt,
            "output_file": str(output_file),
            "model": self.model or "",
            "effort": self.effort or "",
            "schema_file": str(schema_file or ""),
        }

        def fill(template: tuple[str, ...]) -> list[str]:
            return [part.format(**values) for part in template]

        args = [*self.command, *profile.base_args]
        if self.model and profile.model_args:
            args += fill(profile.model_args)
        if self.effort and profile.effort_args:
            args += fill(profile.effort_args)
        if profile.output == "file":
            args += fill(profile.output_file_args)
        if schema_file is not None and profile.schema_args:
            args += fill(profile.schema_args)
        prompt_in_args = any("{prompt}" in part for part in profile.prompt_args)
        if prompt_in_args and _is_batch_file(self.command[0]):
            # cmd.exe re-parses a batch file's arguments: quotes and `&` in the prompt (which includes model
            # output when judging) would run as commands, and newlines would silently truncate it.
            raise ProviderError(
                f"{profile.title} resolves to the batch file {self.command[0]}, which cannot safely receive a "
                "prompt as an argument. Set `command` in the eval config to the real executable "
                '(for example ["node", "<path to the tool>/index.js"]).'
            )
        args += fill(profile.prompt_args)
        return args, None if prompt_in_args else prompt

    def _run(self, prompt: str, workspace: Path, schema: dict[str, Any] | None = None) -> str:
        if self.command is None:
            raise ProviderError(f"{self.profile.title} is not installed")
        with tempfile.TemporaryDirectory(prefix="aipg-out-") as out_dir:
            output_file = Path(out_dir) / "last-message.txt"
            schema_file = None
            if schema is not None and self.profile.schema_args:
                schema_file = Path(out_dir) / "schema.json"
                schema_file.write_text(json.dumps(schema), encoding="utf-8")
            args, stdin = self._args(prompt, output_file, schema_file)
            with self._slots:
                try:
                    completed = subprocess.run(  # noqa: S603 - fixed argument list, no shell
                        args,
                        input=stdin,
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        timeout=self.timeout,
                        cwd=workspace,
                        env=_scrubbed_environment(),
                        check=False,
                    )
                except subprocess.TimeoutExpired as exc:
                    raise ProviderError(f"{self.profile.title} timed out after {self.timeout:.0f}s") from exc
            if completed.returncode != 0:
                detail = (completed.stderr or completed.stdout).strip()[-300:]
                raise ProviderError(f"{self.profile.title} exited with {completed.returncode}: {detail}")
            if self.profile.output == "file":
                if not output_file.is_file():
                    raise ProviderError(f"{self.profile.title} wrote no final message")
                return output_file.read_text(encoding="utf-8").strip()
        return extract_answer(completed.stdout, self.profile.output)

    def run_native(
        self, prompt: str, skill_root: Path | None, append_system_prompt: str, max_turns: int
    ) -> AgentResult:
        # Most CLIs have no system-prompt flag, so the shared persona line is prepended to the prompt in both arms.
        full_prompt = f"{append_system_prompt}\n\n{prompt}" if append_system_prompt else prompt
        with tempfile.TemporaryDirectory(prefix="aipg-run-") as run_dir:
            workspace = Path(run_dir)
            if skill_root is not None:
                target = workspace / self.profile.skills_dir / skill_root.name
                shutil.copytree(skill_root, target, ignore=shutil.ignore_patterns("__pycache__"))
            try:
                text = self._run(full_prompt, workspace)
            except ProviderError as exc:
                return AgentResult(text="", error=str(exc), served_model=self.model or "")
        return AgentResult(text=text, turns=1, stop_reason="completed", served_model=self.model or self.profile.name)

    def complete_json(self, system: str, user: str, schema: dict[str, Any], schema_name: str) -> tuple[Any, Usage]:
        prompt = (
            f"{system}\n\n{user}\n\nReply with only a JSON object that matches this JSON Schema, "
            f"with no other text:\n{json.dumps(schema)}"
        )
        with tempfile.TemporaryDirectory(prefix="aipg-judge-") as run_dir:
            text = self._run(prompt, Path(run_dir), schema)
        payload = extract_json_object(text)
        if payload is None:
            raise ProviderError(f"{self.profile.title} did not return a JSON object")
        return payload, Usage()

    def run_agent(self, *args: Any, **kwargs: Any) -> AgentResult:
        raise ProviderError("agent CLIs load skills natively; the runner uses run_native for this provider")


# ---------------------------------------------------------------------- parsing helpers


def extract_answer(stdout: str, output: str) -> str:
    if output.startswith("json:"):
        field = output.split(":", 1)[1]
        payload = extract_json_object(stdout)
        if payload is None:
            raise ProviderError("expected JSON output but found none")
        if payload.get("error"):
            raise ProviderError(f"tool reported an error: {payload['error']}")
        value = payload.get(field)
        if not isinstance(value, str):
            raise ProviderError(f"JSON output has no '{field}' text")
        return value.strip()
    return stdout.strip()


def extract_json_object(text: str) -> dict[str, Any] | None:
    """Find the last top-level JSON object in free text (tolerates prose and code fences)."""
    decoder = json.JSONDecoder()
    found: dict[str, Any] | None = None
    index = text.find("{")
    while index != -1:
        try:
            value, end = decoder.raw_decode(text, index)
        except json.JSONDecodeError:
            index = text.find("{", index + 1)
            continue
        if isinstance(value, dict):
            found = value
        index = text.find("{", end)
    return found
