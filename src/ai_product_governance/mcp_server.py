"""MCP server: the governance skill for any MCP-capable AI client.

Exposes the skill as
  * tools     - instructions, playbooks, templates, the effective policy, and the two
                deterministic engines (risk tier, unit economics);
  * prompts   - one self-contained prompt per governance workflow;
  * resources - SKILL.md, every playbook and template, and the effective policy.

Security model: every tool is read-only and side-effect free. The policy is fixed when
the server starts (--policy, $AIPG_POLICY or the workspace policy) and can never be
chosen or overridden through a tool argument, so a prompt-injected model cannot point
the server at arbitrary files. Reference and template names are checked against an
allow-list built from the bundle's own directory listing.

Over Streamable HTTP the server can require a bearer token ($AIPG_SERVER_TOKEN or
--token-file), checked by the SDK's own auth middleware, and refuses to listen beyond
loopback without one. --audit-log records every tool call as a JSON line.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
from pathlib import Path
from typing import Any

from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ResourceNotFoundError, ToolError
from mcp_types import ToolAnnotations
from pydantic import AnyHttpUrl

from ai_product_governance import __version__, engines
from ai_product_governance.audit import AuditLog, AuditMiddleware
from ai_product_governance.policy import EffectivePolicy, load_effective_policy
from ai_product_governance.prompts import compose_eval_prompt, compose_workflow_prompt
from ai_product_governance.skill import Skill, load_skill
from ai_product_governance.workflows import EVAL_WORKFLOW, WORKFLOWS, Workflow

SERVER_NAME = "ai-product-governance"
REPOSITORY_URL = "https://github.com/joydeep195/ai-product-governance"

TOKEN_ENV = "AIPG_SERVER_TOKEN"  # noqa: S105 - the variable's name, not a token
MIN_TOKEN_LENGTH = 32
# The audit log's `client.principal` for callers holding the server token.
TOKEN_PRINCIPAL = "shared-token"  # noqa: S105
# The hosts for which the SDK turns on DNS-rebinding protection. Listening anywhere else, including other
# loopback addresses, requires a token.
LOCAL_HOSTS = ("127.0.0.1", "localhost", "::1")

logger = logging.getLogger(__name__)

_READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False)

_MCP_PREAMBLE = """\
> **Using this skill over MCP.** Wherever the instructions below mention a file, use these tools instead:
> `references/<name>.md` -> `get_reference(name)`, `assets/templates/<name>.md` -> `get_template(name)`,
> the policy file -> `get_policy()`, `scripts/risk_tier.py` -> `get_risk_questionnaire()` then
> `classify_risk_tier(answers)`, `scripts/unit_economics.py` -> `calculate_unit_economics(inputs)`.
> The effective policy for this server is **{policy}**.

"""


class ServerConfigError(ValueError):
    """The server was asked to start in an unsafe or unusable configuration."""


class StaticTokenVerifier:
    """Accepts exactly one bearer token. Implements the SDK's `TokenVerifier` protocol."""

    def __init__(self, token: str) -> None:
        self._digest = hashlib.sha256(token.encode("utf-8")).digest()

    async def verify_token(self, token: str) -> AccessToken | None:
        # Comparing fixed-length digests in constant time leaks neither the token nor its length through timing.
        candidate = hashlib.sha256(token.encode("utf-8")).digest()
        if not hmac.compare_digest(candidate, self._digest):
            return None
        # AccessToken requires a token field; a placeholder keeps the secret out of any repr the SDK logs.
        return AccessToken(token="[redacted]", client_id=TOKEN_PRINCIPAL, scopes=[])  # noqa: S106


def build_server(
    policy_path: str | None = None, *, token: str | None = None, audit_log: str | Path | None = None
) -> MCPServer[Any]:
    """Create the MCP server. The policy is resolved once, at start-up.

    `token` makes the Streamable HTTP endpoint require `Authorization: Bearer <token>`; other transports ignore
    it. `audit_log` appends one JSON line per tool call to that file.
    """
    skill = load_skill()
    policy = load_effective_policy(policy_path)
    risk_engine = engines.risk_tier()
    economics_engine = engines.unit_economics()

    middleware = []
    if audit_log is not None:
        try:
            log = AuditLog(audit_log)
        except OSError as exc:
            raise ServerConfigError(f"cannot open --audit-log {audit_log}: {exc.strerror or exc}") from exc
        middleware.append(AuditMiddleware(log, policy))

    verifier = StaticTokenVerifier(token) if token is not None else None
    server: MCPServer[Any] = MCPServer(
        name=SERVER_NAME,
        title="AI Product Governance",
        description="Enterprise AI product governance: fit, economics, evals, risk tiers, controls, launch and operations.",
        version=__version__,
        website_url=REPOSITORY_URL,
        instructions=(
            "Governs AI and LLM features from idea to production. Call get_governance_instructions first, "
            "then load only the playbook for the relevant gate. Use classify_risk_tier and "
            "calculate_unit_economics for tiers and costs instead of estimating them. "
            f"Effective policy: {policy.label}."
        ),
        token_verifier=verifier,
        # The SDK requires an issuer URL, but publishes it only from OAuth routes or protected-resource
        # metadata, and a static-token server enables neither, so a placeholder is enough.
        auth=AuthSettings(issuer_url=AnyHttpUrl("http://localhost"), resource_server_url=None) if verifier else None,
        middleware=middleware,
    )

    _register_tools(server, skill, policy, risk_engine, economics_engine)
    _register_resources(server, skill, policy)
    _register_prompts(server, skill, policy)
    return server


def _register_tools(
    server: MCPServer[Any], skill: Skill, policy: EffectivePolicy, risk_engine: Any, economics_engine: Any
) -> None:
    @server.tool(
        title="Get governance instructions",
        description="Return the operating rules, the six-gate lifecycle router and the output standards. Call this first.",
        annotations=_READ_ONLY,
    )
    def get_governance_instructions() -> str:
        return _MCP_PREAMBLE.format(policy=policy.label) + skill.clean_body

    @server.tool(
        title="Get gate playbook",
        description="Return a playbook (reference) by name. Available: " + ", ".join(skill.reference_names),
        annotations=_READ_ONLY,
    )
    def get_reference(name: str) -> str:
        try:
            return skill.read_reference(name)
        except KeyError as exc:
            raise ToolError(_message(exc)) from exc

    @server.tool(
        title="Get artifact template",
        description="Return an artifact template by name. Available: " + ", ".join(skill.template_names),
        annotations=_READ_ONLY,
    )
    def get_template(name: str) -> str:
        try:
            return skill.read_template(name)
        except KeyError as exc:
            raise ToolError(_message(exc)) from exc

    @server.tool(
        title="Get effective policy",
        description="Return the governance policy this server enforces: tiers, rules, controls, approvers, eval minimums.",
        annotations=_READ_ONLY,
    )
    def get_policy() -> dict[str, Any]:
        return {"policy": policy.document, "source": policy.source, "label": policy.label}

    @server.tool(
        title="Get risk questionnaire",
        description="Return the questions classify_risk_tier expects, with their types and allowed options.",
        annotations=_READ_ONLY,
    )
    def get_risk_questionnaire() -> list[dict[str, Any]]:
        return list(policy.document["questions"])

    @server.tool(
        title="Classify risk tier",
        description=(
            "Deterministically classify an AI use case against the effective policy. `answers` maps question IDs "
            "from get_risk_questionnaire to values. Returns the tier, triggered rules, unanswered questions, required "
            "controls, approvers, eval minimums and the autonomy cap at launch."
        ),
        annotations=_READ_ONLY,
    )
    def classify_risk_tier(answers: dict[str, Any]) -> dict[str, Any]:
        try:
            result: dict[str, Any] = risk_engine.classify(
                policy.document, answers, policy_source=policy.source, policy_path=None
            )
        except risk_engine.AnswerError as exc:
            raise ToolError(f"{exc}. Call get_risk_questionnaire for valid IDs and values.") from exc
        return result

    @server.tool(
        title="Calculate unit economics",
        description=(
            "Price an AI feature per completed task (model cost + review time + expected failure handling). "
            "Required inputs: price_input_per_mtok, price_output_per_mtok, input_tokens_per_call, "
            "output_tokens_per_call, tasks_per_month, success_rate (0-1), baseline_cost_per_task. Optional: "
            "calls_per_task, cache_read_price_per_mtok, cached_input_fraction, other_cost_per_task, "
            "review_minutes_per_task, fallback_minutes_per_failure, loaded_hourly_cost, fixed_monthly_cost, "
            "one_time_cost, currency, label."
        ),
        annotations=_READ_ONLY,
    )
    def calculate_unit_economics(inputs: dict[str, Any]) -> dict[str, Any]:
        try:
            result: dict[str, Any] = economics_engine.calculate(inputs)
        except economics_engine.InputError as exc:
            raise ToolError(str(exc)) from exc
        return result


def _register_resources(server: MCPServer[Any], skill: Skill, policy: EffectivePolicy) -> None:
    @server.resource("aipg://skill", name="SKILL.md", mime_type="text/markdown", description="The skill instructions")
    def skill_document() -> str:
        return skill.clean_body

    @server.resource(
        "aipg://references/{name}", name="Gate playbook", mime_type="text/markdown", description="A gate playbook"
    )
    def reference(name: str) -> str:
        try:
            return skill.read_reference(name)
        except KeyError as exc:
            raise ResourceNotFoundError(_message(exc)) from exc

    @server.resource(
        "aipg://templates/{name}",
        name="Artifact template",
        mime_type="text/markdown",
        description="An artifact template",
    )
    def template(name: str) -> str:
        try:
            return skill.read_template(name)
        except KeyError as exc:
            raise ResourceNotFoundError(_message(exc)) from exc

    @server.resource(
        "aipg://policy", name="Effective policy", mime_type="application/json", description="The enforced policy"
    )
    def policy_document() -> str:
        return json.dumps(policy.document, indent=2)


def _register_prompts(server: MCPServer[Any], skill: Skill, policy: EffectivePolicy) -> None:
    for flow in WORKFLOWS:
        _register_prompt(server, skill, policy, flow)

    def evaluate(options: str = "") -> str:
        return compose_eval_prompt(skill, options)

    server.prompt(name=EVAL_WORKFLOW.id, title=EVAL_WORKFLOW.title, description=EVAL_WORKFLOW.description)(evaluate)


def _register_prompt(server: MCPServer[Any], skill: Skill, policy: EffectivePolicy, flow: Workflow) -> None:
    # The prompt function's parameter name becomes the MCP prompt argument name, so each
    # workflow gets a small adapter with the right signature.
    def render(value: str) -> str:
        return compose_workflow_prompt(skill, flow, value, policy.label)

    adapters = {
        "idea": lambda idea: render(idea),
        "feature": lambda feature: render(feature),
        "status": lambda status: render(status),
        "symptom": lambda symptom: render(symptom),
        "context": lambda context: render(context),
    }
    function = adapters[flow.argument]
    server.prompt(name=flow.id, title=flow.title, description=flow.description)(function)


def _message(exc: KeyError) -> str:
    return str(exc.args[0]) if exc.args else str(exc)


def read_token(token_file: str | None = None) -> str | None:
    """The bearer token from `token_file` if given, else from $AIPG_SERVER_TOKEN, else None."""
    if token_file is not None:
        source = f"--token-file {token_file}"
        try:
            token = _decode_text(Path(token_file).read_bytes()).strip()
        except (OSError, UnicodeDecodeError) as exc:
            reason = exc.strerror if isinstance(exc, OSError) and exc.strerror else str(exc)
            raise ServerConfigError(f"cannot read {source}: {reason}") from exc
        if not token:
            raise ServerConfigError(f"{source} is empty")
    else:
        source = f"${TOKEN_ENV}"
        token = os.environ.get(TOKEN_ENV, "").strip()
        if not token:
            return None
    if any(character.isspace() for character in token):
        raise ServerConfigError(f"the token in {source} must be a single line with no spaces")
    if len(token) < MIN_TOKEN_LENGTH:
        raise ServerConfigError(
            f"the token in {source} is {len(token)} characters; use at least {MIN_TOKEN_LENGTH}, for example "
            '`python -c "import secrets; print(secrets.token_urlsafe(32))"`'
        )
    return token


def _decode_text(data: bytes) -> str:
    # Windows PowerShell writes UTF-16 with a byte-order mark by default, and Notepad may add a UTF-8 one.
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")
    return data.decode("utf-8-sig")


def serve(
    transport: str = "stdio",
    host: str = "127.0.0.1",
    port: int = 8000,
    policy_path: str | None = None,
    *,
    token_file: str | None = None,
    audit_log: str | None = None,
) -> None:
    if transport == "stdio":
        if token_file is not None:
            raise ServerConfigError(
                "--token-file applies to --transport streamable-http; a stdio server talks only to the process "
                "that launched it"
            )
        build_server(policy_path, audit_log=audit_log).run("stdio")
    elif transport == "streamable-http":
        token = read_token(token_file)
        if token is None and host not in LOCAL_HOSTS:
            raise ServerConfigError(
                f"refusing to listen on {host} without authentication: set ${TOKEN_ENV} or pass --token-file, "
                f"or bind to {', '.join(LOCAL_HOSTS)}"
            )
        server = build_server(policy_path, token=token, audit_log=audit_log)
        if token is None:
            logger.warning("No bearer token configured: any process on this machine can call the server")
        else:
            logger.info("Bearer-token authentication is required")
        if audit_log is not None:
            logger.info("Writing an audit line per tool call to %s", audit_log)
        server.run("streamable-http", host=host, port=port)
    else:
        raise ValueError(f"Unsupported transport: {transport}")
